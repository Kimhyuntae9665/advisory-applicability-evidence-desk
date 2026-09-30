# Local prototype runbook

Run npm start and open localhost port 5088. State is fictional and in memory. Stop only this project's process. No UI action calls a model, scans a machine, runs a command from source content or writes external systems. The desk is not a multi-user authenticated production service.

CPU checks: npm test; on Linux, python3 -m unittest discover -s test -p 'test_model_client.py' -v. Transport tests use temporary locks and mocked HTTP; they do not touch the active shared inference lease. Baseline evidence is recorded once by node evaluate.mjs --baseline. Existing artifacts cannot be overwritten silently.

Optional inference requires an explicit coordinator GPU handover. P06 owns the lease during the CPU release. Freeze original gold/erratum, commit the reviewed implementation, run node evaluate.mjs --prepare, then commit model-input.json/source-snapshot.json before requests. Never use evaluator expected claims in prompts. The model explains already verified source facts; it does not independently classify applicability. No development/tuning inference is planned; the frozen evaluation has six cases.

Only after handover and verifying resource/lock/marker state, run python3 model_client.py --lease-authorized. It uses the existing qwen3:4b weights, context4096/output640/timeout60/concurrency1, no thinking, no truncation/shift, and retains every attempt exactly once. No weights, paid services or account changes are required. A blocked marker or busy/unsafe lock prevents HTTP calls.

Timeouts leave a durable shared .blocked marker. If that cannot be written, the process retains the lock. Do not remove a marker, retry under uncertain completion, kill another project's request or infer completion from a desktop disconnect. Verify actual request completion with the owner. No GPU release is safe merely because a client connection failed.

After actual completion, node evaluate.mjs preserves complete/incomplete/invalid JSON/provenance states, citation binding and exact-text copying separately. These are not independent semantic accuracy or safety measures. Record resource/token/duration observations separately from decision quality. Stored-output media makes zero additional inference calls. Semantic inspection of an explanation remains a distinct human action; no model note is automatically accepted.
