# Contributing

Erpel is maintained for our own use. Contributions are welcome; support isn't promised, and we may decline a change that doesn't fit what Erpel is for ([README](README.md)).

## Before you start

- **A vulnerability** goes through [SECURITY.md](SECURITY.md), never an issue.
- **A bug:** open an issue with the bug report form.
- **A new tool, input or behaviour:** open an issue with the feature form first. Erpel's tools have a fixed purpose; generic operations are out of scope, however useful they would be ([REQ-001-PRS-F006](docs/specs/req-001-core.md#req-001-prs-f006-no-generic-operations)).

## How a change is made

1. **Spec first:** a change to an operation starts in its area spec ([specs index](docs/specs/README.md)).
2. **Tests first,** where a spec's Definition of Done describes the behaviour.
3. **The code,** with the checks of the [development guide](docs/guides/development.md) passing locally.
4. **A changelog line** for a behaviour change.

The development guide's [rules for changes](docs/guides/development.md#rules-for-changes) say each of these in full, and [AGENTS.md](AGENTS.md), the rules for coding agents, holds the rules every change follows, such as keeping deployment facts and secrets out of the repository.

## Commits and pull requests

Commits follow [Conventional Commits](https://www.conventionalcommits.org/), one topic per commit. The pull request template lists what review looks for.

## Licence

Erpel is licensed under [Apache-2.0](LICENSE). Unless you state otherwise, a contribution you submit for inclusion is licensed under Apache-2.0 without additional terms (section 5 of the licence); there is no separate agreement and no sign-off line.
