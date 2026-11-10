import { Link } from 'react-router-dom';
import { EmptyState, PageHeader } from '../components/ui';

export function NotFoundPage() {
  return (
    <div>
      <PageHeader title="Page not found" crumbs={[{ label: 'Not found' }]} />
      <EmptyState>
        The requested page does not exist.{' '}
        <Link to="/" className="link">
          Back to the dashboard
        </Link>
      </EmptyState>
    </div>
  );
}
