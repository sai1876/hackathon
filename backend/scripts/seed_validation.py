import math

def equivalent(expected,actual):
 if isinstance(expected,dict):return isinstance(actual,dict) and set(expected)==set(actual) and all(equivalent(v,actual[k]) for k,v in expected.items())
 if isinstance(expected,list):return isinstance(actual,list) and len(expected)==len(actual) and all(equivalent(a,b) for a,b in zip(expected,actual))
 if isinstance(expected,float):return isinstance(actual,(float,int)) and math.isclose(expected,actual,rel_tol=1e-12,abs_tol=1e-10)
 return expected==actual
