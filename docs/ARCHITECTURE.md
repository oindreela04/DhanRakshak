# DhanRakshak Architecture

## Product boundary

DhanRakshak is an intelligence and orchestration layer across payment failures, checkout abandonment, subscription failures, overdue invoices, promise-to-pay commitments, and customer payment behavior. It does not replace Razorpay payment processing and it does not make financial decisions exclusively through an LLM.

## Runtime flow

1. Razorpay Test Mode or a deterministic demo adapter emits events.
2. A webhook gateway authenticates, deduplicates, and stores raw events.
3. Normalization converts provider payloads into domain events.
4. Identity resolution links provider identities to a customer.
5. Customer recovery memory supplies prior behavior and outcomes.
6. Risk and root-cause engines estimate exposure and likely failure cause.
7. Recovery probability and economics rank possible interventions by expected incremental value.
8. Policy Guard applies deterministic limits, consent, frequency, eligibility, and approval rules.
9. The Recovery Agent executes only an approved bounded action through a provider adapter.
10. Payment verification confirms the outcome before revenue is counted.
11. Incrementality measurement separates recovered value from baseline behavior and records the result.
12. Memory and audit logs are updated for future decisions and review.

## Customer Recovery DNA

`RecoveryMemoryService` builds one persisted JSON snapshot per customer from verified transaction, recovery, invoice, and promise-to-pay facts. It tracks payment-method and channel success, action success, recovery duration and attempts, preferred behavior, invoice delay, promise reliability, opt-out rate, fatigue, recovered value, risk exposure, last outcomes, and confidence. `update_after_recovery()` accepts only verified/success/recovered outcomes and recalculates the customer snapshot; the API exposes it at `GET /api/v1/customers/{customer_id}/recovery-dna`. Missing customers return `404 CUSTOMER_NOT_FOUND`, and a customer with no history receives zero-valued rates rather than fabricated statistics.

## Safety boundaries

ML and LLM outputs are predictions or explanations. They are persisted with model metadata and confidence, but never authorize money movement by themselves. Execution requires deterministic backend policy evaluation and provider-side verification. The initial `DemoAdapter` and `RazorpayAdapter` only define the integration boundary; live provider calls are intentionally not implemented.

## Data model

The initial SQLAlchemy schema contains customers, payment and billing objects, recovery events/actions/outcomes, customer memory, prediction records, policies, promises, notifications, experiments, model versions, webhooks, and audit logs. Foreign keys and indexes support the primary customer, event, status, and processing paths without prematurely encoding complex relationships.
