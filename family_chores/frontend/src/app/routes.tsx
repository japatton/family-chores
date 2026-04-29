import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'
import { MemberRewards } from '../views/MemberRewards'
import { MemberView } from '../views/MemberView'
import { ParentView } from '../views/ParentView'
import { TodayView } from '../views/TodayView'

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<TodayView />} />
        <Route path="/member/:slug" element={<MemberView />} />
        <Route path="/member/:slug/rewards" element={<MemberRewards />} />
        <Route path="/parent/*" element={<ParentView />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
