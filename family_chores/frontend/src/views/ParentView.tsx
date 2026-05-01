import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import clsx from 'clsx'
import { useParentStore } from '../store/parent'
import { ActivityTab } from './parent/ActivityTab'
import { ApprovalQueue } from './parent/ApprovalQueue'
import { CalendarTab } from './parent/CalendarTab'
import { ChoresTab } from './parent/ChoresTab'
import { MembersTab } from './parent/MembersTab'
import { ParentGate } from './parent/ParentGate'
import { RewardsTab } from './parent/RewardsTab'

export function ParentView() {
  const clearToken = useParentStore((s) => s.clear)

  return (
    <ParentGate>
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex items-center justify-between gap-4 flex-wrap">
          <h1 className="text-fluid-xl font-black text-brand-900">Parent mode</h1>
          <button
            type="button"
            onClick={clearToken}
            className="min-h-touch px-5 rounded-2xl font-bold text-fluid-sm bg-brand-50 text-brand-700"
          >
            Lock
          </button>
        </header>

        <nav className="flex gap-2 flex-wrap">
          <ParentTabLink to="approvals">Approvals</ParentTabLink>
          <ParentTabLink to="rewards">Rewards</ParentTabLink>
          <ParentTabLink to="calendar">Calendar</ParentTabLink>
          <ParentTabLink to="members">Members</ParentTabLink>
          <ParentTabLink to="chores">Chores</ParentTabLink>
          <ParentTabLink to="activity">Activity</ParentTabLink>
        </nav>

        <Routes>
          <Route path="approvals" element={<ApprovalQueue />} />
          <Route path="rewards" element={<RewardsTab />} />
          <Route path="calendar" element={<CalendarTab />} />
          <Route path="members" element={<MembersTab />} />
          <Route path="chores" element={<ChoresTab />} />
          <Route path="activity" element={<ActivityTab />} />
          <Route path="*" element={<Navigate to="approvals" replace />} />
        </Routes>
      </div>
    </ParentGate>
  )
}

function ParentTabLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        clsx(
          'min-h-touch px-5 rounded-2xl font-bold text-fluid-sm grid place-items-center',
          isActive
            ? 'bg-brand-600 text-white'
            : 'bg-brand-50 text-brand-700 hover:bg-brand-100',
        )
      }
    >
      {children}
    </NavLink>
  )
}
