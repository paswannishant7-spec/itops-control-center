import { auditEventPageSchema } from './auditApi'

describe('auditEventPageSchema', () => {
  it('accepts normalized, content-minimized audit events', () => {
    const page = auditEventPageSchema.parse({
      items: [
        {
          id: '73bb9477-5b69-4ee5-aacf-e80ed38a2520',
          source: 'AI',
          action: 'ai.feedback.accepted',
          entity_type: 'TICKET',
          entity_id: '63bb9477-5b69-4ee5-aacf-e80ed38a2520',
          actor_id: null,
          before_state: null,
          after_state: { confidence: 0.9 },
          reason: 'Reviewed',
          request_id: null,
          created_at: '2026-09-13T10:00:00Z',
        },
      ],
      total: 1,
      offset: 0,
      limit: 50,
    })
    expect(page.items[0].source).toBe('AI')
  })
})
