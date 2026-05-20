# Contributing to DevSecCode Scanner

Thanks for your interest. Here's what's welcome and what isn't, so we can
both spend our time well.

## Welcome

- **Bug reports.** Open an [issue](https://github.com/DevSecCode/DevSecCode-NPM/issues/new/choose).
  Include the version (`devseccode --version`), your platform, the command
  you ran, and what you saw vs. what you expected. False positives and
  false negatives are bugs — please report them with the smallest snippet
  that reproduces the problem.
- **Feature requests.** Open an issue with the use case. We read every
  one; we don't always reply immediately.
- **Rule suggestions.** If there's a CWE pattern you wish we caught, file
  an issue with a minimal repro (please scrub any real secrets).
- **Documentation fixes.** Typos, broken links, unclear instructions — PRs
  for these are welcome.
- **Security disclosures** — see below.

## Not accepted

The DevSecCode Scanner is licensed under a proprietary EULA
(see [LICENSE.txt](./LICENSE.txt)) that does not grant rights to
redistribute, modify, or create derivative works. As a result:

- **Code PRs** that change the scanner's behavior, the rule library, or
  output formats are not accepted. We can't merge them under the license,
  and we'd rather tell you upfront than have you spend hours on a patch.
- **Forks**, while permitted for personal viewing, may not be
  redistributed or used as the basis of a competing scanner.

This isn't a "we'll change our minds someday" — it's how the license
works. We're being explicit so nobody is surprised.

## Security disclosures

Found a vulnerability in the scanner itself? Please don't open a public
issue. Use [GitHub's private security advisory form](https://github.com/DevSecCode/DevSecCode-NPM/security/advisories/new)
to report it, and we'll triage privately.

## Where conversations happen

- **Bug reports + features:** [GitHub Issues](https://github.com/DevSecCode/DevSecCode-NPM/issues)
- **General questions + show-and-tell:** [GitHub Discussions](https://github.com/DevSecCode/DevSecCode-NPM/discussions)
- **The IDE product** (full rule library, compliance, SBOM, evidence
  packages, POA&M, remediation workflows): [devseccode.com](https://devseccode.com)
