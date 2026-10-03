import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { errorMessage } from '../../api/client'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useAuth } from '../auth/authContextValue'
import { directoryApi, type Department, type Location } from './directoryApi'

export function TeamsPanel({
  departments,
  locations,
}: {
  departments: Department[]
  locations: Location[]
}) {
  const { user, accessToken } = useAuth()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [candidateSearch, setCandidateSearch] = useState('')
  const [membershipReason, setMembershipReason] = useState('')
  const [notice, setNotice] = useState('')
  const debouncedCandidateSearch = useDebouncedValue(candidateSearch.trim())
  const canManage = user?.permissions.includes('team:manage') ?? false
  const teams = useQuery({
    queryKey: ['directory-teams', user?.id],
    queryFn: ({ signal }) => directoryApi.teams(accessToken, signal),
    retry: false,
  })
  const detail = useQuery({
    queryKey: ['directory-team', user?.id, selectedId],
    queryFn: ({ signal }) =>
      directoryApi.team(accessToken, selectedId!, signal),
    enabled: selectedId !== null,
    retry: false,
  })
  const candidates = useQuery({
    queryKey: [
      'directory-candidates',
      user?.id,
      selectedId,
      debouncedCandidateSearch,
    ],
    queryFn: ({ signal }) =>
      directoryApi.candidates(
        accessToken,
        selectedId!,
        debouncedCandidateSearch,
        signal,
      ),
    enabled:
      canManage && selectedId !== null && detail.data?.status === 'ACTIVE',
    retry: false,
  })
  const invalidate = async (teamId?: string) => {
    await queryClient.invalidateQueries({
      queryKey: ['directory-teams', user?.id],
    })
    if (teamId) {
      await queryClient.invalidateQueries({
        queryKey: ['directory-team', user?.id, teamId],
      })
      await queryClient.invalidateQueries({
        queryKey: ['directory-candidates', user?.id, teamId],
      })
    }
  }
  const create = useMutation({
    mutationFn: (body: object) => directoryApi.createTeam(accessToken, body),
    onSuccess: async (team) => {
      setSelectedId(team.id)
      await invalidate(team.id)
      setNotice(`${team.name} was created.`)
    },
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) =>
      directoryApi.updateTeam(accessToken, id, body),
    onSuccess: async (team) => {
      await invalidate(team.id)
      setNotice(`${team.name} was updated.`)
    },
  })
  const assign = useMutation({
    mutationFn: ({
      userId,
      memberRole,
    }: {
      userId: string
      memberRole: string
    }) =>
      directoryApi.assignMember(
        accessToken,
        selectedId!,
        userId,
        memberRole,
        membershipReason,
      ),
    onSuccess: async (member) => {
      await invalidate(selectedId!)
      setMembershipReason('')
      setNotice(`${member.display_name} was assigned to the team.`)
    },
  })
  const remove = useMutation({
    mutationFn: (userId: string) =>
      directoryApi.removeMember(
        accessToken,
        selectedId!,
        userId,
        membershipReason,
      ),
    onSuccess: async () => {
      await invalidate(selectedId!)
      setMembershipReason('')
      setNotice('Team membership ended; its history was retained.')
    },
  })

  function createTeam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice('')
    const form = new FormData(event.currentTarget)
    create.mutate({
      code: String(form.get('code')),
      name: String(form.get('name')),
      description: String(form.get('description') ?? '') || null,
      department_id: String(form.get('department_id') ?? '') || null,
      location_id: String(form.get('location_id') ?? '') || null,
      reason: String(form.get('reason')),
    })
  }

  return (
    <section className="directory-panel directory-panel-wide" id="teams">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Support organization</p>
          <h2>Teams</h2>
        </div>
        <span>{teams.data?.length ?? 0} teams</span>
      </div>
      {teams.isPending && <p role="status">Loading teams…</p>}
      {teams.error && (
        <p role="alert">
          {errorMessage(teams.error)}{' '}
          <button type="button" onClick={() => void teams.refetch()}>
            Retry
          </button>
        </p>
      )}
      {teams.data?.length === 0 && (
        <p className="empty-state">No support teams are configured.</p>
      )}
      {teams.data && teams.data.length > 0 && (
        <div className="team-grid" aria-label="Support teams">
          {teams.data.map((team) => (
            <button
              type="button"
              key={team.id}
              className={
                selectedId === team.id ? 'team-card selected' : 'team-card'
              }
              onClick={() => {
                setSelectedId(team.id)
                setNotice('')
              }}
            >
              <span>
                <code>{team.code}</code>
                <span className={`status-pill ${team.status.toLowerCase()}`}>
                  {team.status}
                </span>
              </span>
              <strong>{team.name}</strong>
              <small>
                {team.member_count} members ·{' '}
                {team.department?.name ?? 'No department'}
              </small>
            </button>
          ))}
        </div>
      )}

      {canManage && (
        <details className="management-details">
          <summary>Create support team</summary>
          <form className="management-form form-grid" onSubmit={createTeam}>
            <label>
              Code
              <input name="code" required minLength={2} maxLength={32} />
            </label>
            <label>
              Name
              <input name="name" required minLength={2} maxLength={160} />
            </label>
            <label className="full-field">
              Description
              <textarea name="description" maxLength={500} />
            </label>
            <OrganizationSelectors
              departments={departments}
              locations={locations}
            />
            <label className="full-field">
              Reason for creation
              <textarea name="reason" required minLength={3} maxLength={500} />
            </label>
            <button disabled={create.isPending}>
              {create.isPending ? 'Creating…' : 'Create team'}
            </button>
            {create.error && <p role="alert">{errorMessage(create.error)}</p>}
          </form>
        </details>
      )}

      {selectedId && (
        <section className="record-editor" aria-labelledby="team-detail-title">
          {detail.isPending && <p role="status">Loading team detail…</p>}
          {detail.error && <p role="alert">{errorMessage(detail.error)}</p>}
          {detail.data && (
            <>
              <div className="panel-heading">
                <div>
                  <h3 id="team-detail-title">{detail.data.name}</h3>
                  <p>{detail.data.description || 'No description provided.'}</p>
                </div>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setSelectedId(null)}
                >
                  Close
                </button>
              </div>
              <div className="table-wrap">
                <table>
                  <caption>Active technician assignments</caption>
                  <thead>
                    <tr>
                      <th scope="col">Technician</th>
                      <th scope="col">Team role</th>
                      <th scope="col">System role</th>
                      {canManage && <th scope="col">Action</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.data.members.map((member) => (
                      <tr key={member.user_id}>
                        <td>
                          <strong>{member.display_name}</strong>
                          <small>{member.email}</small>
                        </td>
                        <td>{member.member_role}</td>
                        <td>{member.roles.join(', ')}</td>
                        {canManage && (
                          <td>
                            <button
                              className="text-button danger-text"
                              type="button"
                              disabled={
                                remove.isPending ||
                                membershipReason.trim().length < 3
                              }
                              onClick={() => remove.mutate(member.user_id)}
                            >
                              End assignment for {member.display_name}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                    {detail.data.members.length === 0 && (
                      <tr>
                        <td colSpan={canManage ? 4 : 3}>
                          No active technicians.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {canManage && (
                <>
                  <form
                    className="management-form form-grid"
                    key={detail.data.updated_at}
                    onSubmit={(event) => {
                      event.preventDefault()
                      const form = new FormData(event.currentTarget)
                      update.mutate({
                        id: detail.data.id,
                        body: {
                          name: String(form.get('name')),
                          description:
                            String(form.get('description') ?? '') || null,
                          department_id:
                            String(form.get('department_id') ?? '') || null,
                          location_id:
                            String(form.get('location_id') ?? '') || null,
                          status: String(form.get('status')),
                          reason: String(form.get('reason')),
                        },
                      })
                    }}
                  >
                    <h4 className="full-field">Team configuration</h4>
                    <label>
                      Name
                      <input
                        name="name"
                        required
                        defaultValue={detail.data.name}
                      />
                    </label>
                    <label>
                      Status
                      <select name="status" defaultValue={detail.data.status}>
                        <option value="ACTIVE">Active</option>
                        <option value="INACTIVE">Inactive</option>
                      </select>
                    </label>
                    <label className="full-field">
                      Description
                      <textarea
                        name="description"
                        maxLength={500}
                        defaultValue={detail.data.description ?? ''}
                      />
                    </label>
                    <OrganizationSelectors
                      departments={departments}
                      locations={locations}
                      departmentId={detail.data.department?.id}
                      locationId={detail.data.location?.id}
                    />
                    <label className="full-field">
                      Reason for team change
                      <textarea
                        name="reason"
                        required
                        minLength={3}
                        maxLength={500}
                      />
                    </label>
                    <button disabled={update.isPending}>
                      {update.isPending ? 'Saving…' : 'Save team'}
                    </button>
                    {update.error && (
                      <p role="alert">{errorMessage(update.error)}</p>
                    )}
                  </form>
                  {detail.data.status === 'ACTIVE' && (
                    <form
                      className="membership-form"
                      onSubmit={(event) => {
                        event.preventDefault()
                        const form = new FormData(event.currentTarget)
                        assign.mutate({
                          userId: String(form.get('candidate')),
                          memberRole: String(form.get('member_role')),
                        })
                      }}
                    >
                      <h4>Assign technician</h4>
                      <label>
                        Find eligible technicians
                        <input
                          value={candidateSearch}
                          onChange={(event) =>
                            setCandidateSearch(event.target.value)
                          }
                          placeholder="Name, email or employee number"
                        />
                      </label>
                      <label>
                        Technician
                        <select name="candidate" required defaultValue="">
                          <option value="" disabled>
                            Select an active technician
                          </option>
                          {candidates.data?.map((candidate) => (
                            <option key={candidate.id} value={candidate.id}>
                              {candidate.display_name} —{' '}
                              {candidate.roles.join(', ')}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Team-level role
                        <select name="member_role" defaultValue="MEMBER">
                          <option value="MEMBER">Member</option>
                          <option value="LEAD">Lead</option>
                        </select>
                      </label>
                      <label>
                        Reason for membership change
                        <input
                          value={membershipReason}
                          onChange={(event) =>
                            setMembershipReason(event.target.value)
                          }
                          required
                          minLength={3}
                          maxLength={500}
                        />
                      </label>
                      <button
                        disabled={
                          assign.isPending ||
                          candidates.isPending ||
                          membershipReason.trim().length < 3
                        }
                      >
                        {assign.isPending ? 'Assigning…' : 'Assign technician'}
                      </button>
                      {candidates.isPending && (
                        <p role="status">Loading candidates…</p>
                      )}
                      {candidates.error && (
                        <p role="alert">{errorMessage(candidates.error)}</p>
                      )}
                      {assign.error && (
                        <p role="alert">{errorMessage(assign.error)}</p>
                      )}
                      {remove.error && (
                        <p role="alert">{errorMessage(remove.error)}</p>
                      )}
                    </form>
                  )}
                </>
              )}
            </>
          )}
        </section>
      )}
      {notice && <p role="status">{notice}</p>}
    </section>
  )
}

function OrganizationSelectors({
  departments,
  locations,
  departmentId = '',
  locationId = '',
}: {
  departments: Department[]
  locations: Location[]
  departmentId?: string
  locationId?: string
}) {
  return (
    <>
      <label>
        Department
        <select name="department_id" defaultValue={departmentId}>
          <option value="">No department</option>
          {departments
            .filter(
              (item) => item.status === 'ACTIVE' || item.id === departmentId,
            )
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Location
        <select name="location_id" defaultValue={locationId}>
          <option value="">No location</option>
          {locations
            .filter(
              (item) => item.status === 'ACTIVE' || item.id === locationId,
            )
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
        </select>
      </label>
    </>
  )
}
