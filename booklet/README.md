# Question booklets for human solvers

- `creasebench-questions.pdf`: all 185 tasks, one numbered question each (key: `key.json`).
- `creasebench-expert-questions.pdf`: the 34 headline `expert` tasks only (key: `key-expert.json`).

The key files map question numbers to task ids. Don't give them to solvers, because some ids name the answer.
Full input files are in `tasks/`, or regenerate everything with
`python -m creasebench.booklet --out booklet/ [--splits expert]`, which also writes `inputs/Qnnn/`.
