# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Which versions are currently supported with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please send an email to: [SECURITY_EMAIL]

Please include the following information:

- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue

We will acknowledge your email within 24 hours, and will send a more detailed response within 48 hours indicating the next steps in handling your report.

## Disclosure Policy

- Once we receive a vulnerability report, our team will initiate an investigation
- We will not disclose the vulnerability until a fix is available
- We will keep you informed of our progress
- Public disclosure will be made after the fix is released

## Security Best Practices

When deploying Paperless-AIssist:

1. **Keep credentials secure** - Never commit API tokens to version control
2. **Use environment variables** - Store sensitive data in environment variables
3. **Network isolation** - Consider running in an isolated network segment
4. **Regular updates** - Keep the application updated to the latest version
5. **Monitor access** - Review logs regularly for suspicious activity
