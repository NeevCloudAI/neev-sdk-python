# Changesets

This directory is managed by [Changesets](https://github.com/changesets/changesets).

To record a change for the next release, run:

```sh
npx @changesets/cli
```

Pick the affected bump (patch/minor/major) and write a short summary. The commit
that lands the changeset drives the version bump and `CHANGELOG.md` entry when
the release workflow runs.
