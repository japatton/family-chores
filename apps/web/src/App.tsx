/**
 * Phase 3 placeholder. This file gets replaced with the real cloud-hosted
 * web app once SaaS auth + the multi-tenant routes land. Until then it
 * exists so the workspace can be tested end-to-end (vite build + vitest)
 * without anyone wondering what the empty scaffold should look like.
 *
 * See DECISIONS §11 step 11.
 */

export function App() {
  return (
    <main
      style={{
        fontFamily: 'system-ui, sans-serif',
        maxWidth: '32rem',
        margin: '4rem auto',
        padding: '0 1rem',
        lineHeight: 1.5,
      }}
    >
      <h1>Family Chores</h1>
      <p>The cloud-hosted web app is coming soon.</p>
      <p>
        For now, the project ships as a Home Assistant add-on. See the
        <a
          href="https://github.com/japatton/family-chores"
          rel="noreferrer"
          style={{ marginLeft: '0.25rem' }}
        >
          repository
        </a>{' '}
        for installation.
      </p>
    </main>
  )
}
