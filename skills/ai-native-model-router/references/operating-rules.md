# Operating rules

1. Every request explicitly selects a profile. The bundled `gpt6` profile is
   inactive by default and requires explicit-owner-selection. The retired
   `gpt5.6` profile is rejected. The gpt6 profile contains only OpenAI routes;
   `writer.high-volume-deterministic` is not a supported route/v2 slot.
2. Preserve route/v1 independence and version pairing; mixed versions fail closed.
3. For gpt6 on route/v2, R1 uses `gpt-6.1-sol:low`, R2 uses
   `gpt-6.1-sol:medium`, and R3 uses `gpt-6.1-sol:high`. Each is ONE review,
   including R3, per the owner's explicit 2026-09-23 selection; the Sol model
   was upgraded on 2026-10-02 with reasoning levels preserved. Same-model
   review is allowed and reported; it is not independent validation.
4. Unknown availability stays unknown. An unavailable assurance route blocks;
   there are no alternate assurance models in gpt6. A substantive review
   rejection is not a transport failure; create a new candidate before revalidation.
5. Accepted route-bound failure evidence is only model-not-found,
   authenticated-provider-outage, quota-exhaustion, or
   repeated-bounded-transport-failure. The legacy route/v1 fallback requires accepted evidence
   and an available next route.
6. Provider execution, credentials and transport remain outside this package.
   Always return enforcement_status: not-executed; resolution is not execution.
