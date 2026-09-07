"""Small dynamic SCM. All equation inputs refer to the previous time step."""
import ast
import hashlib
import json
import math
import operator
import random

VERSION = '0.1.0'
OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
       ast.Mult: operator.mul, ast.Div: operator.truediv}


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Expected a finite number')
    return float(value)


def expression(source, names):
    if not isinstance(source, str) or len(source) > 1000:
        raise ValueError('Equation must be a string of at most 1000 characters')
    tree = ast.parse(source, mode='eval').body
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError('Equation too large')
    def check(node):
        if isinstance(node, ast.Constant):
            number(node.value)
        elif isinstance(node, ast.Name) and node.id in names:
            pass
        elif isinstance(node, ast.BinOp) and type(node.op) in OPS:
            check(node.left)
            check(node.right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            check(node.operand)
        else:
            raise ValueError('Unsupported expression or unknown input')
    check(tree)
    return tree


def evaluate(node, values):
    if isinstance(node, ast.Constant):
        return number(node.value)
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.UnaryOp):
        return (-1 if isinstance(node.op, ast.USub) else 1) * evaluate(node.operand, values)
    return number(OPS[type(node.op)](evaluate(node.left, values), evaluate(node.right, values)))


def prepare(model):
    variables, parameters = model['variables'], model.get('parameters', {})
    names = set(variables) | set(parameters)
    if not variables or set(variables) & set(parameters) or 'u' in names:
        raise ValueError('Variables and parameters must be nonempty/disjoint; u is reserved')
    if any(not name.isidentifier() for name in names):
        raise ValueError('Names must be identifiers')
    for spec in parameters.values():
        number(spec['mean'])
        if number(spec.get('sd', 0)) < 0:
            raise ValueError('Negative parameter sd')
    trees = {}
    for name, spec in variables.items():
        number(spec['initial'])
        if number(spec.get('noise_sd', 0)) < 0:
            raise ValueError('Negative noise sd')
        trees[name] = expression(spec['equation'], names | {'u'})
    return trees


def graph(model):
    """Derive temporal edges directly from equation references."""
    return [{'from': parent, 'to': target, 'lag': 1}
            for target, tree in prepare(model).items()
            for parent in sorted({n.id for n in ast.walk(tree)
                                  if isinstance(n, ast.Name) and n.id in model['variables']})]


def simulate(model, *, steps=12, draws=500, seed=1, initial=None, interventions=None):
    trees = prepare(model)
    if type(steps) is not int or not 1 <= steps <= 1000:
        raise ValueError('steps must be 1..1000')
    if type(draws) is not int or not 1 <= draws <= 10000:
        raise ValueError('draws must be 1..10000')
    initial, interventions = initial or {}, interventions or {}
    variables = sorted(trees)
    if set(initial) - set(variables) or set(interventions) - set(variables):
        raise ValueError('Unknown variable')
    for value in initial.values():
        number(value)
    for spec in interventions.values():
        number(spec['value'])
        start, end = spec['start'], spec['end']
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= steps:
            raise ValueError('Interventions use inclusive steps 1..steps')
    rng = random.Random(seed)
    sums = [{name: [0.0, 0.0] for name in variables} for _ in range(steps + 1)]
    for _ in range(draws):
        params = {name: rng.gauss(spec['mean'], spec.get('sd', 0))
                  for name, spec in sorted(model.get('parameters', {}).items())}
        state = {name: number(initial.get(name, model['variables'][name]['initial'])) for name in variables}
        for t in range(steps + 1):
            if t:
                previous, state = state, {}
                for name in variables:
                    # Consume noise even under intervention to pair scenario randomness.
                    noise = rng.gauss(0, model['variables'][name].get('noise_sd', 0))
                    action = interventions.get(name)
                    if action and action['start'] <= t <= action['end']:
                        state[name] = number(action['value'])
                    else:
                        state[name] = evaluate(trees[name], {**previous, **params, 'u': noise})
            for name, value in state.items():
                sums[t][name][0] += value
                sums[t][name][1] += value * value
    return [{name: {'mean': s / draws, 'sd': math.sqrt(max(0, ss / draws - (s / draws)**2))}
             for name, (s, ss) in row.items()} for row in sums]


def compare(model, **request):
    request = {'steps': 12, 'draws': 500, 'seed': 1, 'initial': {}, 'interventions': {}, **request}
    baseline = simulate(model, **{**request, 'interventions': {}})
    intervention = simulate(model, **request)
    fingerprint = hashlib.sha256(json.dumps(model, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {'runner_version': VERSION, 'model_sha256': fingerprint, 'request': request,
            'graph': graph(model), 'baseline': baseline, 'intervention': intervention,
            'final_mean_delta': {name: intervention[-1][name]['mean'] - baseline[-1][name]['mean']
                                 for name in model['variables']}}
