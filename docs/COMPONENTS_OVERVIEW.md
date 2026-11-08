   # AI Taskvector components overview

    Layer:                                              Messaging: ZeroMQ
    -----------------------------------------------------------------------
    Muli-agent loop poller Layer                                          |
     (services/agentic_loop/..)                         -> Pub/Sub API    |                 
    ----------------------------------------------------------------------|
    Single agent loop runtime Layer                                       |
     (agents/..; agents/chat/turn_driver.py)                              |
      - agent roles,                                                      |
      - tools,                                                            |
      - orchestration,                                                    | GUI
      - semantics, etc.                                 -> Pub/Sub API    |                  
    ----------------------------------------------------------------------|
    Workflow server Layer                                                 |
     (workflow_server.py)                               -> Pub/Sub API    |          
    ______________________________________________________________________|             
    Low-code framework layer                                              |
     (runtime/run.py, runtime/executor.py)                                |
                                                        -> run.py/Pub API |
