# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in `neevai`, please report it
privately. **Do not open a public GitHub issue for security reports.**

- Email **security@neevcloud.com** with details, or
- Use GitHub's private vulnerability reporting for this repository.

Please include:

- A description of the issue and its impact
- Steps to reproduce or a proof of concept
- Affected version(s) of the SDK

We aim to acknowledge reports within **3 business days** and to provide a
remediation timeline after triage. We will coordinate a disclosure date with you
and credit you in the release notes unless you prefer to remain anonymous.

## Supported versions

The SDK is pre-1.0. Security fixes are released against the latest published
`0.x` version. Once `1.0` ships, this policy will be updated with a support
window for prior majors.

## Handling credentials

`neevai` is a server-side SDK. Never embed a NeevAI API key in client-side
or browser code, and never commit keys to version control. Use environment
variables (`NEEVCLOUD_API_KEY`) or a secrets manager.
