# STUDIQS® SmartParent™ - Frontend Client (Mobile PWA & Web)

## Architecture Overview
- **Framework**: Modern Responsive Mobile-First Client (PWA)
- **Target Platforms**: Android (APK/PWA), iOS (Safari PWA), Desktop Responsive
- **Key Modules**:
  1. `/auth`: Mobile OTP Verification & Multi-Device Session State
  2. `/dashboard`: Student Academic Profile & Holistic Subject Cards
  3. `/diagnostics`: Topic Mastery, Gap Analysis, & Performance Heatmaps
  4. `/voice`: Voice Query Assistant (Ask STUDIQS Natural Language RAG Interface)
  5. `/reports`: Consolidated Diagnostic Reports & PTM Handoff PDFs
  6. `/marketplace`: Diagnostic Question Papers & Expert Evaluation Booking

## DPDP Act 2023 Compliance
- Service Worker excludes private telemetry endpoints (`/api/v1/*`) from browser `CacheStorage`.
- Ephemeral session tokens stored strictly in secure memory / HttpOnly contexts.

