"""Self-contained small HiGHS reproducer. Requires only highspy + Python stdlib.

Examples:
  python standalone_repro.py baseline --output-dir NEW_DIRECTORY
  python standalone_repro.py all --output-dir NEW_DIRECTORY
  python standalone_repro.py mps --output-dir NEW_DIRECTORY

Five cases: baseline, presolve_on, tight_tolerance, proved_y_bound, mps.
Each selected case runs once with a 10-second limit. Output must be a new
directory. Other HiGHS versions are allowed with an untested-version warning.
The mathematical model and all actual loaded coefficients are checked before
solving. No existing output is overwritten and no package is installed.
"""
import argparse
from fractions import Fraction as F
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
import time

REFERENCE_VERSION='1.15.1'
CASES=('baseline','presolve_on','tight_tolerance','proved_y_bound','mps')
K=F.from_float(0.000002)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def filehash(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def expected_model(bounded_y=False):
    names=['g','f','r','y','v']+['z'+str(i) for i in range(6)]
    upper=['1','1000','1000',str(K) if bounded_y else '1000']+['1']*7
    variables=[dict(id=name,kind='continuous' if j<4 else 'binary',lb='0',ub=upper[j])
               for j,name in enumerate(names)]
    def row(name,a,lower='0'):
        return dict(id=name,a=a,constant='0',lb=lower,ub='0')
    rows=[row('k_balance',{'r':'1','f':'-1','g':str(-K)}),
          row('y_balance',{'r':'1','f':'-1','y':'-1'}),
          row('gate',{'g':'1','v':'-1'},None),
          row('subset',{'z0':'525','z1':'560','z2':'779','z3':'955','z4':'131','z5':'229','v':'-1470'})]
    return dict(schema='paper15.sparse_exact_model.v1',numeric_contract='canonical_rational_projection',
                variables=variables,rows=rows,objective=dict(a={'g':'1'},constant='0',sense='max'))


def build_api_lp(hs,model):
    variables,rows=model['variables'],model['rows']
    names=[v['id'] for v in variables]
    lp=hs.HighsLp();lp.num_col_=11;lp.num_row_=4;lp.sense_=hs.ObjSense.kMaximize
    lp.col_names_=names;lp.row_names_=[r['id'] for r in rows]
    lp.col_cost_=[1.0]+[0.0]*10;lp.col_lower_=[0.0]*11
    lp.col_upper_=[float(F(v['ub'])) for v in variables]
    lp.row_lower_=[0.0,0.0,-hs.kHighsInf,0.0];lp.row_upper_=[0.0]*4
    lp.integrality_=[hs.HighsVarType.kContinuous]*4+[hs.HighsVarType.kInteger]*7
    start=[0];indices=[];values=[]
    for name in names:
        for j,row in enumerate(rows):
            if name in row['a']:indices.append(j);values.append(float(F(row['a'][name])))
        start.append(len(values))
    lp.a_matrix_.format_=hs.MatrixFormat.kColwise;lp.a_matrix_.start_=start
    lp.a_matrix_.index_=indices;lp.a_matrix_.value_=values
    return lp


def export_actual(hs,lp):
    """Read the full installed model; do not infer it from the producer arrays."""
    names=list(lp.col_names_);row_names=list(lp.row_names_)
    if len(names)!=lp.num_col_ or len(row_names)!=lp.num_row_:raise ValueError('Loaded names are incomplete')
    if lp.a_matrix_.format_!=hs.MatrixFormat.kColwise:raise ValueError('Unsupported loaded matrix orientation')
    def number(value):
        value=float(value)
        return str(F.from_float(value)) if math.isfinite(value) else None
    variables=[]
    for j,name in enumerate(names):
        kind=lp.integrality_[j] if lp.integrality_ else hs.HighsVarType.kContinuous
        lo,hi=number(lp.col_lower_[j]),number(lp.col_upper_[j])
        if kind==hs.HighsVarType.kContinuous:domain='continuous'
        elif kind==hs.HighsVarType.kInteger:
            domain='binary' if lo is not None and hi is not None and 0<=F(lo)<=F(hi)<=1 else 'integer'
        else:raise ValueError('Unsupported loaded integer type')
        variables.append(dict(id=name,kind=domain,lb=lo,ub=hi))
    rows=[dict(id=name,a={},constant='0',lb=number(lp.row_lower_[j]),ub=number(lp.row_upper_[j]))
          for j,name in enumerate(row_names)]
    a=lp.a_matrix_
    for j,name in enumerate(names):
        for position in range(a.start_[j],a.start_[j+1]):
            i=a.index_[position]
            if name in rows[i]['a']:raise ValueError('Duplicate loaded matrix entry')
            rows[i]['a'][name]=number(a.value_[position])
    objective=dict(a={name:number(lp.col_cost_[j]) for j,name in enumerate(names) if lp.col_cost_[j]!=0},
                   constant=number(lp.offset_),sense='max' if lp.sense_==hs.ObjSense.kMaximize else 'min')
    return dict(schema='paper15.sparse_exact_model.v1',numeric_contract='canonical_rational_projection',
                variables=variables,rows=rows,objective=objective)


def exact_certificate(model):
    """Evaluate the explicit integer witness in the actual loaded model."""
    point={v['id']:F(0) for v in model['variables']}
    point.update(g=F(1),r=K,y=K,v=F(1),z1=F(1),z2=F(1),z4=F(1))
    for v in model['variables']:
        value=point[v['id']]
        if not F(v['lb'])<=value<=F(v['ub']):raise ValueError('Witness bound failure')
        if v['kind']=='binary' and value not in (0,1):raise ValueError('Witness binary failure')
    for row in model['rows']:
        value=F(row['constant'])+sum((F(c)*point[i] for i,c in row['a'].items()),F(0))
        if row['lb'] is not None and value<F(row['lb']):raise ValueError('Witness row lower failure')
        if row['ub'] is not None and value>F(row['ub']):raise ValueError('Witness row upper failure')
    objective=model['objective']
    if objective!=dict(a={'g':'1'},constant='0',sense='max'):raise ValueError('Objective changed')
    g=next(v for v in model['variables'] if v['id']=='g')
    if g['ub']!='1' or point['g']!=1:raise ValueError('Matching primal/upper bound failed')
    return dict(model_sha256=digest(model),objective_sha256=digest(objective),
                point={i:str(v) for i,v in point.items()},lower_bound='1',upper_bound='1',exact_optimum='1',
                upper_premise=dict(variable='g',side='ub',value='1'),
                reason='Full integer witness attains the declared objective bound g<=1.')


def run_case(hs,case,out,environment,plan_hash,mps):
    model=expected_model(case=='proved_y_bound');h=hs.Highs()
    settings=dict(threads=1,random_seed=0,time_limit=10.0,
                  presolve='on' if case=='presolve_on' else 'off',log_dev_level=1,
                  log_file=str(out/(case+'.log')))
    if case=='tight_tolerance':settings['mip_feasibility_tolerance']=1e-9
    readback={}
    for name,value in settings.items():
        if h.setOptionValue(name,value)!=hs.HighsStatus.kOk:raise RuntimeError('Option rejected: '+name)
        status,actual=h.getOptionValue(name)
        if status!=hs.HighsStatus.kOk or actual!=value:raise RuntimeError('Option readback mismatch: '+name)
        readback[name]=actual
    for name in ('mip_feasibility_tolerance','primal_feasibility_tolerance','dual_feasibility_tolerance',
                 'mip_rel_gap','mip_abs_gap','parallel','solver'):
        status,value=h.getOptionValue(name)
        if status!=hs.HighsStatus.kOk:raise RuntimeError('Default option readback failed: '+name)
        readback[name]=value
    status=h.readModel(str(mps)) if case=='mps' else h.passModel(build_api_lp(hs,model))
    if status!=hs.HighsStatus.kOk:raise RuntimeError('Model loading failed')
    actual=export_actual(hs,h.getLp())
    if actual!=model:raise RuntimeError('Full loaded model differs from the stated small reproducer')
    certificate=exact_certificate(actual)
    save_new(out/(case+'_actual_model.json'),actual)
    save_new(out/(case+'_exact_certificate.json'),certificate)
    save_new(out/(case+'_ATTEMPT.json'),dict(case=case,max_solves=1,plan_sha256=plan_hash,
                actual_model_sha256=digest(actual),full_readback_matches_definition=True))
    print(json.dumps(dict(case=case,environment=environment,settings_readback=readback,
                         actual_model_sha256=digest(actual),exact_optimum='1')),flush=True)
    start=time.perf_counter();run_status=h.run();seconds=time.perf_counter()-start
    info=h.getInfo();solution=h.getSolution();status=h.getModelStatus()
    values=list(map(float,solution.col_value));names=[v['id'] for v in actual['variables']]
    returned=dict(model_sha256=digest(actual),point={n:str(F.from_float(x)) for n,x in zip(names,values,strict=True)},
                  binary64_hex={n:x.hex() for n,x in zip(names,values,strict=True)})
    save_new(out/(case+'_returned_point.json'),returned)
    record=dict(case=case,environment=environment,options_readback=readback,
        run_status=str(run_status),model_status=h.modelStatusToString(status),
        objective=float(info.objective_function_value),mip_node_count=int(info.mip_node_count),
        mip_gap=float(info.mip_gap),mip_dual_bound=float(info.mip_dual_bound),seconds=seconds,
        actual_model_sha256=digest(actual),full_readback_matches_definition=True,
        exact_certificate_sha256=digest(certificate),returned_point_sha256=digest(returned),
        plan_sha256=plan_hash,highs_run_calls=1,exact_optimum_from_independent_mathematics='1')
    save_new(out/(case+'_RESULT.json'),record)
    print(json.dumps(dict(case=case,status=record['model_status'],objective=record['objective'],
                          nodes=record['mip_node_count'],exact_optimum='1')),flush=True)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case',nargs='?',default='baseline',choices=(*CASES,'all'))
    parser.add_argument('--output-dir',required=True,help='New directory for private runtime records')
    parser.add_argument('--highspy-path',help='Optional existing installation directory; nothing is installed')
    parser.add_argument('--mps',default=str(Path(__file__).with_name('small_repro_17digit.mps')))
    args=parser.parse_args()
    out=Path(args.output_dir).resolve();mps=Path(args.mps).resolve()
    if out.exists():parser.error('Output directory already exists; refusing to overwrite it')
    if args.highspy_path:sys.path.insert(0,args.highspy_path)
    import highspy as hs
    version_probe=hs.Highs()
    try:package_version=importlib.metadata.version('highspy')
    except importlib.metadata.PackageNotFoundError:package_version='unavailable'
    environment=dict(os=platform.system(),os_release=platform.release(),os_version=platform.version(),
        machine=platform.machine(),python_version=sys.version,python_implementation=platform.python_implementation(),
        highspy_package_version=package_version,highs_version=version_probe.version(),highs_git_hash=version_probe.githash())
    warning=None
    if environment['highs_version']!=REFERENCE_VERSION:
        warning='Untested HiGHS version: '+environment['highs_version']+'. The saved reference observation uses Windows HiGHS 1.15.1; results may differ.'
        print('WARNING: '+warning,file=sys.stderr,flush=True)
    cases=list(CASES) if args.case=='all' else [args.case]
    if 'mps' in cases and not mps.is_file():parser.error('MPS file does not exist')
    out.mkdir(parents=True,exist_ok=False)
    plan=dict(schema='small-reproducer-run-plan-v1',created_before_solves=True,cases=cases,max_solves=len(cases),
        per_case_time_limit_seconds=10,seed=0,threads=1,environment=environment,untested_version_warning=warning,
        code_sha256=filehash(Path(__file__)),mps_sha256=filehash(mps) if 'mps' in cases else None,
        models={case:digest(expected_model(case=='proved_y_bound')) for case in cases},
        reference_observation_version=REFERENCE_VERSION,other_versions_tested_by_this_bundle=False,
        input_contract='binary64 coefficient interpreted as its exact Fraction; decimal model is distinguished by exact_check.py')
    save_new(out/'PLAN.json',plan);plan_hash=filehash(out/'PLAN.json')
    print(json.dumps(dict(environment=environment,cases=cases,max_solves=len(cases),plan_sha256=plan_hash)),flush=True)
    records=[run_case(hs,case,out,environment,plan_hash,mps) for case in cases]
    save_new(out/'SUMMARY.json',dict(highs_run_calls=len(records),cases=[dict(case=r['case'],status=r['model_status'],
                  objective=r['objective'],nodes=r['mip_node_count']) for r in records],plan_sha256=plan_hash,
                  code_sha256=filehash(Path(__file__)),environment=environment))


if __name__=='__main__':main()
