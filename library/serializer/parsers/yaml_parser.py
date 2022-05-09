import re
import inspect
from types import FunctionType, CodeType

FLOAT_REGEX = "-?\d+\.\d+"
INT_REGEX = "\d+"
STR_REGEX = "\'(.*)\'"
KEY_VAL_REGEX = "(.*):([\s\S]*)"


def to_yaml(obj, indent=0):
    if obj is None:
        return "null"
    elif isinstance(obj, bool):
        return str(obj).lower()
    elif isinstance(obj, (int, float)):
        return str(obj)
    elif isinstance(obj, str):
        return "\'" + obj.replace('\\', '\\\\').replace('\n', '\\n') + "\'"
    elif isinstance(obj, list):
        if not obj:
            return "[]"
        else:
            res = ""
            for o in obj:
                res += f"{' ' * indent}- {to_yaml(o, indent + 2)}\n"
            return res[indent:-1]
    elif isinstance(obj, dict):
        res = ""
        if not obj:
            return "{}"
        for key, val in obj.items():
            str_val = to_yaml(val, indent + 2)
            if isinstance(val, (list, dict)) and val:
                str_val = "\n" + " " * (indent + 2) + str_val
            res += f"{' ' * indent}{to_yaml(key)}: {str_val}\n"
        return res[indent:-1]
    else:
        raise ValueError(f"Wrong type {type(obj)}")


def from_yaml(s, indent=0):
    s = s.strip("\n ")
    if s == "null":
        return None
    elif s == "[]":
        return []
    elif s == "{}":
        return {}
    elif s == "false" or s == "true":
        return s[0] == 't'
    elif re.fullmatch(INT_REGEX, s):
        return int(s)
    elif re.fullmatch(FLOAT_REGEX, s):
        return float(s)
    elif re.fullmatch(STR_REGEX, s):
        return re.fullmatch(STR_REGEX, s).group(1).replace('\\n', '\n').replace('\\\\', '\\')
    else:
        a = split(s, indent)
        is_list = False
        for i in range(len(a)):
            a[i] = a[i].strip("\n ")
            if a[i][0:2] == "- ":
                is_list = True
        if is_list:
            res = []
        else:
            res = {}
        for s in a:
            if is_list:
                res.append(from_yaml(s[2:], indent + 2))
            else:
                m = re.fullmatch(KEY_VAL_REGEX, s)
                if m is None:
                    raise ValueError(f"Wrong string \"{s}\"")
                key = m.group(1)
                val = m.group(2)
                res[from_yaml(key)] = from_yaml(val, indent + 2)
        return res


def split(s, indent):
    a = []
    tmp = ""
    for i in range(len(s)):
        if i+indent+1 < len(s) and s[i] == "\n" and s[i+1:i+indent+1] == " " * indent and s[i+indent+1] != " ":
            a.append(tmp)
            tmp = ""
        else:
            tmp += s[i]
    a.append(tmp)
    return a



TYPE = "**type**"
VALUE = "**value**"

CODE_FIELD_NAME = "__code__"
GLOBAL_FIELD_NAME = "__globals__"

FUNCTION_ATTRS_NAMES = [
    "__code__",
    "__name__",
    "__defaults__",
    "__closure__",
]

CODE_OBJECT_ARGS = [
    'co_argcount',
    'co_posonlyargcount',
    'co_kwonlyargcount',
    'co_nlocals',
    'co_stacksize',
    'co_flags',
    'co_code',
    'co_consts',
    'co_names',
    'co_varnames',
    'co_filename',
    'co_name',
    'co_firstlineno',
    'co_lnotab',
    'co_freevars',
    'co_cellvars'
]


def serialize(obj):
    result = {}
    tp = type(obj)
    tp_name = tp.__name__
    if obj is None or isinstance(obj, (int, float, complex, bool, str)):
        return obj
    elif tp == dict:
        allStr = True
        for key, val in obj.items():
            if not isinstance(key, str):
                allStr = False
        if allStr:
            for key, val in obj.items():
                result[key] = serialize(val)
        else:
            result[TYPE] = tp_name
            result[VALUE] = []
            for key, val in obj.items():
                result[VALUE].append([serialize(key), serialize(val)])
    elif tp == list or tp == tuple:
        result[TYPE] = tp_name
        result[VALUE] = []
        for o in obj:
            result[VALUE].append(serialize(o))
    elif inspect.isroutine(obj):
        result[TYPE] = tp_name
        result[VALUE] = serialize_function(obj)
    elif tp == bytes:
        result[TYPE] = tp_name
        result[VALUE] = list(obj)
    elif tp == type:
        result[TYPE] = tp_name
        result[VALUE] = serialize_class(obj)
    elif hasattr(obj, "__dict__"):
        result[TYPE] = "class_object"
        result[VALUE] = serialize_class_obj(obj)
    else:
        result[TYPE] = tp_name
        result[VALUE] = serialize_inst(obj)
    return result


def serialize_function(f: object):
    result = {}
    for detail in inspect.getmembers(f):
        if inspect.isbuiltin(detail[1]):
            continue
        if detail[0] in FUNCTION_ATTRS_NAMES:
            result[detail[0]] = serialize(detail[1])
            if detail[0] == CODE_FIELD_NAME:
                result[GLOBAL_FIELD_NAME] = {}
                glob = f.__getattribute__(GLOBAL_FIELD_NAME)
                for name in detail[1].__getattribute__('co_names'):
                    if name == f.__name__:
                        result[GLOBAL_FIELD_NAME][name] = f.__name__
                        continue
                    if name in __builtins__:
                        continue
                    if name in glob:
                        if inspect.ismodule(glob[name]):
                            continue
                        result[GLOBAL_FIELD_NAME][name] = serialize(glob[name])
    return result


def deserialize(obj):
    result = {}
    tp = type(obj)

    if tp == dict:
        if VALUE in obj and TYPE in obj:
            if obj[TYPE] == "list":
                result = []
                for o in obj[VALUE]:
                    result.append(deserialize(o))
                return result
            elif obj[TYPE] == "tuple":
                result = []
                for o in obj[VALUE]:
                    result.append(deserialize(o))
                return tuple(result)
            elif obj[TYPE] == "dict":
                for pr in obj[VALUE]:
                    result[deserialize(pr[0])] = deserialize(pr[1])
                return result
            elif obj[TYPE] == 'function':
                return deserialize_function(obj[VALUE])
            elif obj[TYPE] == 'bytes':
                return bytes(obj[VALUE])
            elif obj[TYPE] == 'type':
                return deserialize_class(obj[VALUE])
            elif obj[TYPE] == 'class_object':
                return deserialize_class_obj(obj[VALUE])
            return obj[VALUE]
        for name, o in obj.items():
            result[name] = deserialize(o)
    else:
        return obj
    return result


def deserialize_function(f: dict):
    code_fields = f[CODE_FIELD_NAME][VALUE]
    code_args = []
    for field in CODE_OBJECT_ARGS:
        arg = code_fields[field]
        if type(arg) == dict:
            code_args.append(deserialize(arg))
        else:
            code_args.append(arg)
    details = [CodeType(*code_args)]
    glob = {'__builtins__': __builtins__}
    for name, o in f[GLOBAL_FIELD_NAME].items():
        glob[name] = deserialize(o)
    details.append(glob)
    for attr in FUNCTION_ATTRS_NAMES:
        if attr == CODE_FIELD_NAME:
            continue
        details.append(deserialize(f[attr]))

    result_func = FunctionType(*details)
    if result_func.__name__ in result_func.__getattribute__(GLOBAL_FIELD_NAME):
        result_func.__getattribute__(GLOBAL_FIELD_NAME)[result_func.__name__] = result_func
    return result_func


def serialize_inst(inst: object):
    res = {}
    for attr in inspect.getmembers(inst):
        if not callable(attr[1]):
            res[attr[0]] = serialize(attr[1])
    return res


def serialize_class(cls):
    bases = ()
    for i in cls.__bases__:
        if i.__name__ != "object":
            bases += (serialize_class(i),)
    args = serialize(dict(cls.__dict__))
    return {"name": cls.__name__, "bases": serialize(bases), "content": args}


def deserialize_class(cls):
    return type(deserialize(cls["name"]), deserialize(cls["bases"]), deserialize(cls["content"]))


def serialize_class_obj(obj):
    return {
        "class": serialize_class(obj.__class__),
        "vars": serialize(obj.__dict__)
    }


def deserialize_class_obj(obj):
    res = deserialize_class(obj["class"])()
    res.__dict__ = deserialize(obj["vars"])
    return res