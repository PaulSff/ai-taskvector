# `list_dir` tool

Discover the content of a local folder and provide it in a structured easy-to-read format + schema, e.g.: 

- Output from ListDir unit (data port): 
```json
{"path": "/home/user/documents", 
 "content": 
     {
       "dirs": ["work", "personal"], 
       "files": ["notes.txt", "budget.xlsx"]
     }
}
```
Schema (interpreted by LLM):
```
/tools/list_dir -> 
├── __init__.py
├── follow_ups.py
├── list_dir_workflow.json
├── prompt.py
└── tool.yaml
```

## Parser action

See `prompt.py`. Side channel key on `parser_output` is `list_dir`.


## Follow-up

`run_list_dir_follow_up` in `__init__.py` → `TOOL_RUNNERS["list_dir"]` in `registry.py`.
