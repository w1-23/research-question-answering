# Research Question Answering

`research-question-answering` is a portable Agent Skill for finding and citing evidence for a research question. It uses the host's permitted source tools and accepts evidence already available to the host. The host decides scope, routes, answer sufficiency and when to stop.

Use CPython 3.11 or newer. The method and helpers have no third-party dependencies. Install the repository root as a Skill directory named `research-question-answering`, or run the standalone checks from the repository root.

```sh
python3 -m unittest discover -s tests -v
python3 -m examples.web_only_host
```

The example loads the same Python helpers in a web-only replay host. Its data is synthetic and changing host permission is modeled by capability injection. The example makes no network calls.

- [Skill entry](SKILL.md) describes trigger, reuse, targeted reads and stopping conditions.
- [Host API](references/host-capabilities.md) documents `discover`, `read_selected`, `citation_packet` and normalized results.
- [CitrusScholar mapping](CAPABILITY_MIGRATION.md) lists the baseline bindings and host verification work.

## Changes

- Initial release. Adds the method, a bounded callback API, evidence selection and independent synthetic tests.
