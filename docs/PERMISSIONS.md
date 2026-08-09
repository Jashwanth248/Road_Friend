# Permission and Privacy Model

Road Friend uses a capability-based permission broker.

## Principles

1. Public web and map searches do not imply access to private user data.
2. Local files are never enumerated automatically. The browser file picker is the access boundary.
3. Gmail is protected by Google OAuth and Road Friend also asks for session permission before reading.
4. External side effects such as sending email or Messages require one-time confirmation.
5. Tokens and OAuth credential files are local-only and ignored by Git.
6. Driving-awareness output is informational and must not override the physical road environment.

## Permission lifecycle

```text
User request
   ↓
Does it require private data or side effect?
   ├─ No → execute tool
   └─ Yes
       ↓
   Ask user
       ↓
   Allow / Deny
       ├─ Deny → cancel
       └─ Allow
            ↓
       OS/OAuth/file picker if required
            ↓
       Execute only the approved action
```

## File access

When the user asks to read a document, Road Friend asks permission and then opens the browser file picker. The server receives only the selected file bytes. It does not scan directories.

## Gmail

Google OAuth remains the account-authorization layer. Road Friend adds a conversational permission layer on top:

- reading: session grant;
- sending: one confirmation per email.

## Messages

The optional macOS Messages sender is disabled unless `ALLOW_MACOS_MESSAGES=true` is set locally. Every send still requires confirmation.
