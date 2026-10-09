"""Self-contained, read-only, standard-library proof checker for the small model.

python exact_check.py
python exact_check.py --records DIRECTORY_CREATED_BY_standalone_repro

The default command proves optimum 1 separately for decimal k=1/500000 and
the exact rational value of binary64 0.000002, including the proved y<=k case.
--records also checks each fully read-back API/MPS input and its saved witness.
No solver, reproducer module, debugger, large model or network is used.
"""
import argparse
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path


def need(condition,message):
    if not condition:raise ValueError(message)


def q(value):
    need(type(value) is str,'Exact numbers must be rational strings')
    result=Q(value);need(str(result)==value,'Noncanonical rational string')
    return result


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def filehash(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            need(key not in result,'Duplicate JSON key');result[key]=value
        return result
    def reject(value):raise ValueError('Nonfinite JSON constant')
    return json.loads(path.read_bytes(),object_pairs_hook=unique,parse_constant=reject)


def stated_model(k,bounded_y=False):
    names=['g','f','r','y','v','z0','z1','z2','z3','z4','z5']
    variables=[]
    for name in names:
        binary=name in ('v','z0','z1','z2','z3','z4','z5')
        upper='1' if binary or name=='g' else str(k) if bounded_y and name=='y' else '1000'
        variables.append({'id':name,'kind':'binary' if binary else 'continuous','lb':'0','ub':upper})
    rows=[{'id':'k_balance','a':{'r':'1','f':'-1','g':str(-k)},'constant':'0','lb':'0','ub':'0'},
          {'id':'y_balance','a':{'r':'1','f':'-1','y':'-1'},'constant':'0','lb':'0','ub':'0'},
          {'id':'gate','a':{'g':'1','v':'-1'},'constant':'0','lb':None,'ub':'0'},
          {'id':'subset','a':{'z0':'525','z1':'560','z2':'779','z3':'955','z4':'131','z5':'229','v':'-1470'},
           'constant':'0','lb':'0','ub':'0'}]
    return {'schema':'paper15.sparse_exact_model.v1','numeric_contract':'canonical_rational_projection',
            'variables':variables,'rows':rows,'objective':{'a':{'g':'1'},'constant':'0','sense':'max'}}


def witness(k):
    return {'g':'1','f':'0','r':str(k),'y':str(k),'v':'1','z0':'0','z1':'1','z2':'1','z3':'0','z4':'1','z5':'0'}


def evaluate(model,point):
    need(type(point) is dict and set(point)=={v['id'] for v in model['variables']},'Full coordinate coverage')
    x={i:q(value) for i,value in point.items()};violations=[]
    for v in model['variables']:
        value=x[v['id']]
        if v['kind']=='binary' and value not in (0,1):violations.append([v['id'],'binary'])
        if not q(v['lb'])<=value<=q(v['ub']):violations.append([v['id'],'bounds'])
    for row in model['rows']:
        value=q(row['constant'])+sum((q(a)*x[i] for i,a in row['a'].items()),Q(0))
        if row['lb'] is not None and value<q(row['lb']):violations.append([row['id'],'lb',str(q(row['lb'])-value)])
        if row['ub'] is not None and value>q(row['ub']):violations.append([row['id'],'ub',str(value-q(row['ub']))])
    o=model['objective'];objective=q(o['constant'])+sum((q(c)*x[i] for i,c in o['a'].items()),Q(0))
    return {'status':'VALID' if not violations else 'INVALID','objective':str(objective),'violations':violations,
            'variables_checked':len(x),'binary_domains_checked':sum(v['kind']=='binary' for v in model['variables']),
            'rows_checked':len(model['rows'])}


def prove(model,k,bounded_y=False,point=None):
    need(model==stated_model(k,bounded_y),'Full model differs from the stated small reproducer')
    need(k>0,'Positive k')
    point=witness(k) if point is None else point
    result=evaluate(model,point)
    need(result['status']=='VALID' and result['objective']=='1','Exact objective-one witness failed')
    objective=model['objective'];g=next(v for v in model['variables'] if v['id']=='g')
    need(objective=={'a':{'g':'1'},'constant':'0','sense':'max'} and q(g['ub'])==1,'Upper bound g<=1')
    # Independently sum the first equality minus the second, then add k*g<=k.
    combined={};rhs=Q(0)
    for row,weight in ((model['rows'][0],Q(1)),(model['rows'][1],Q(-1))):
        need(row['lb'] is not None and q(row['lb'])==q(row['ub']),'Equality premise')
        rhs+=weight*(q(row['ub'])-q(row['constant']))
        for i,a in row['a'].items():combined[i]=combined.get(i,Q(0))+weight*q(a)
    combined={i:a for i,a in combined.items() if a}
    need(combined=={'g':-k,'y':Q(1)} and rhs==0,'Identity y=k*g')
    combined['g']+=k;rhs+=k*q(g['ub'])
    need({i:a for i,a in combined.items() if a}=={'y':Q(1)} and rhs==k,'Proved y upper bound')
    return {'model_sha256':digest(model),'k':str(k),'bounded_y':bounded_y,'witness':result,
            'lower_bound':'1','upper_bound':'1','exact_optimum':'1','proved_identity':'y=k*g','proved_y_upper':str(rhs)}


def check_records(folder):
    plan=read(folder/'PLAN.json');names=plan['cases'];kb=Q.from_float(0.000002)
    allowed={'baseline','presolve_on','tight_tolerance','proved_y_bound','mps'}
    need(type(names) is list and len(set(names))==len(names) and set(names)<=allowed,'Unknown/duplicate case')
    need(1<=len(names)<=5 and plan['max_solves']==len(names) and plan['per_case_time_limit_seconds']==10,'Run limits')
    checks=[]
    for name in names:
        actual=read(folder/(name+'_actual_model.json'));cert=read(folder/(name+'_exact_certificate.json'))
        record=read(folder/(name+'_RESULT.json'));attempt=read(folder/(name+'_ATTEMPT.json'))
        returned=read(folder/(name+'_returned_point.json'))
        need(digest(actual)==plan['models'][name]==record['actual_model_sha256']==cert['model_sha256']==attempt['actual_model_sha256'],'Input identity')
        need(cert['objective_sha256']==digest(actual['objective']),'Objective identity')
        need(record['exact_certificate_sha256']==digest(cert),'Certificate identity')
        need(record['plan_sha256']==attempt['plan_sha256']==filehash(folder/'PLAN.json'),'Plan binding')
        need(record['highs_run_calls']==attempt['max_solves']==1,'Single planned solve')
        need(cert['lower_bound']==cert['upper_bound']==cert['exact_optimum']=='1','Declared optimum')
        proof=prove(actual,kb,name=='proved_y_bound',cert['point'])
        settings=record['options_readback']
        need(settings['threads']==1 and settings['random_seed']==0 and settings['time_limit']==10.0,'Recorded solve settings')
        need(settings['presolve']==('on' if name=='presolve_on' else 'off'),'Presolve setting')
        if name=='tight_tolerance':need(settings['mip_feasibility_tolerance']==1e-9,'Tight tolerance')
        need(digest(returned)==record['returned_point_sha256'] and returned['model_sha256']==digest(actual),'Returned point identity')
        need(set(returned['point'])==set(returned['binary64_hex']),'Returned hexadecimal coordinates')
        for i,value in returned['point'].items():
            floating=float.fromhex(returned['binary64_hex'][i])
            need(math.isfinite(floating) and Q.from_float(floating)==q(value),'Returned rational/binary64 identity')
        diagnostic=evaluate(actual,returned['point'])
        checks.append({'case':name,'proof':proof,'environment':record['environment'],
                       'solver_status':record['model_status'],'solver_objective':record['objective'],
                       'zero_optimal_contradicted':record['model_status']=='Optimal' and record['objective']==0,
                       'returned_point_exact':diagnostic})
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--records')
    args=parser.parse_args()
    kd,kb=Q(1,500000),Q.from_float(0.000002)
    proofs=[dict(number_contract=label,proof=prove(stated_model(k,bounded),k,bounded))
            for label,k in [('decimal',kd),('binary64',kb)] for bounded in (False,True)]
    # A point for decimal k is not silently treated as a binary64-model point.
    different=evaluate(stated_model(kb),witness(kd))
    need(kd!=kb and different['status']=='INVALID','Number-contract distinction')
    result={'status':'PASS','checker_sha256':filehash(Path(__file__)),'proofs':proofs,
            'decimal_minus_binary64_k':str(kd-kb),'decimal_witness_on_binary64_model':different,
            'actual_run_checks':check_records(Path(args.records)) if args.records else [],
            'imports_reproducer':False,'imports_solver':False,'solver_calls':0,'files_written':0,
            'scope':'This stated 11-variable four-row model only; no minimality or other-version reproducibility claim.'}
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':main()
