import { useToday } from '../api/hooks'
import { MemberTile } from '../components/MemberTile'

export function TodayView() {
  const today = useToday()

  if (today.isLoading) {
    return (
      <div className="grid place-items-center min-h-[40vh] text-fluid-base text-brand-700">
        Loading…
      </div>
    )
  }
  if (today.error) {
    return (
      <div className="grid place-items-center min-h-[40vh] text-fluid-base text-rose-700">
        Couldn't reach the backend.
      </div>
    )
  }

  const members = today.data?.members ?? []
  if (members.length === 0) {
    return (
      <div className="grid place-items-center min-h-[50vh] text-center max-w-xl mx-auto">
        <div>
          <div className="text-fluid-3xl mb-4" aria-hidden>👪</div>
          <div className="text-fluid-xl font-black text-brand-900">
            Add your first family member
          </div>
          <p className="mt-4 text-fluid-base text-brand-700">
            Tap <span className="font-bold">Parent</span> at the top to set a
            PIN, then add members and chores. Kids tap their tile to see
            what's up today.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-[100rem]">
      <h1 className="text-fluid-xl font-black text-brand-900 mb-6 sm:mb-10">
        Today
      </h1>
      <div className="grid gap-6 sm:gap-8 grid-cols-1 md:grid-cols-2">
        {members.map((m) => (
          <MemberTile key={m.id} member={m} />
        ))}
      </div>
    </div>
  )
}
