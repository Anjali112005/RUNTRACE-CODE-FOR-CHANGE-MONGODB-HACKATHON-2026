import { Link } from 'react-router-dom';
import { EmptyState } from '../components/ui';

export function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      description="That page does not exist in RunTrace."
      action={<Link to="/" className="btn-primary">Back to overview</Link>}
    />
  );
}
