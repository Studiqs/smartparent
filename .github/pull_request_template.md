## 🎯 Title Format
<!-- e.g. feat(auth): implement OTP cooldown boundary and salted hashing -->
<!-- e.g. fix(rls): resolve indirect child subquery policy for evidence records -->

## 📝 Summary of Changes
- 

## 🛡️ Target Branch
- [ ] `staging` (Standard feature / bugfix delivery)
- [ ] `main` (Production release from verified staging only)

## 🧪 Testing Evidence (Mandatory)
<!-- Paste local terminal test output showing passed tests -->
```bash
# e.g. python -m pytest tests/unit/...
```

- [ ] All unit & integration tests passed locally
- [ ] No regression introduced
- [ ] Linter & formatter check passed (`ruff check .` / `npm run lint`)
- [ ] Zero hardcoded secrets, API keys, or tokens in git diff

## 🔒 Security & Privacy Checklist (DPDP Act 2023)
- [ ] Row-Level Security (RLS) respected for all new queries
- [ ] Tenant boundaries isolated (`subscriber_id` / `child_id`)
- [ ] Ephemeral data or OTPs never logged or exposed in responses
- [ ] PWA cache exclusions maintained for private student endpoints

## 👤 Reviewer Gate
- **Lead Approval**: Required from CODEOWNERS before merge.

