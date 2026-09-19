Currently Working on a project that involves creating a Workflow Graph that drafts an email on a given topic and can self improve on it self

Draft Graph

START -> Drafter -> Evaluator-> if_node - > Drafter or Finalizer -> END

Things to add:
- fix logic (done)
- Feedback so it will not just return a number but rather a feedback message. (done)
- Add a saving mechanism like sqllite and checkpointers.
- add a counter to prevent api usage (mostly done)

Things i learned:
- Proper use and naming of nodes and initializing of names and edges
- Implementing counters to prevent infinite loops and errors