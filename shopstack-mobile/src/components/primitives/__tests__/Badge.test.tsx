/**
 * Render tests for src/components/primitives/Badge.tsx.
 *
 * Evidence tier: T2 (executes the real component through react-test-renderer;
 * native deps are mocked in jest.setup.js). Confirms the shared "decision badge"
 * language (buy/skip/use-soon/compare/...) renders its label and the null-guard
 * behaves when no token color is supplied.
 */
import { render, screen } from '@testing-library/react-native';
import { Badge } from '../Badge';

describe('Badge', () => {
  it('renders the label text for a decision kind', () => {
    render(<Badge kind="buy" label="Need milk" />);
    expect(screen.getByText('Need milk')).toBeTruthy();
  });

  it('renders the label for an explicit color override (bypassing decision tokens)', () => {
    render(<Badge color={{ fg: '#FFFFFF', bg: '#000000' }} label="Override color" />);
    expect(screen.getByText('Override color')).toBeTruthy();
  });

  it('returns null when neither kind nor color is provided (null-guard)', () => {
    const { queryByText } = render(<Badge label="ghost" />);
    expect(queryByText('ghost')).toBeNull();
  });

  it('renders a large-size badge', () => {
    render(<Badge kind="skip" label="Skip this" size="lg" />);
    expect(screen.getByText('Skip this')).toBeTruthy();
  });

  it('renders each decision kind without crashing', () => {
    const kinds = ['buy', 'skip', 'useSoon', 'compare', 'confirm', 'watch'] as const;
    for (const kind of kinds) {
      const { unmount } = render(<Badge kind={kind} label={kind} />);
      expect(screen.getByText(kind)).toBeTruthy();
      unmount();
    }
  });
});
