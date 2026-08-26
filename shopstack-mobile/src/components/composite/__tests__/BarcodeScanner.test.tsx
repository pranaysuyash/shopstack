/**
 * Tests for src/components/composite/BarcodeScanner.tsx.
 *
 * Evidence tier: T2 (executes the real component through react-test-renderer;
 * expo-camera is mocked because the native camera + permission prompt cannot
 * run under jest-expo). Guards the permission-state machine that was previously
 * broken by `CameraView.requestCameraPermissionsAsync` (removed in expo-camera
 * ~16) — regression coverage for that defect.
 */
import { render, screen, waitFor } from '@testing-library/react-native';
import { BarcodeScanner } from '../BarcodeScanner';

// expo-camera native module + permission prompt cannot run in jest-expo.
jest.mock('expo-camera', () => {
  const React = require('react');
  return {
    CameraView: (props: Record<string, unknown>) => React.createElement('CameraView', props),
    Camera: {
      requestCameraPermissionsAsync: jest.fn(),
    },
  };
});

// Isolated from the network; the component calls lookupBarcode on a scan.
jest.mock('../../../api/barcode', () => ({
  lookupBarcode: jest.fn(() => Promise.resolve(null)),
}));

import { Camera } from 'expo-camera';

describe('BarcodeScanner permission flow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('requests camera permission when shown and renders the camera when granted', async () => {
    (Camera.requestCameraPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'granted' });

    render(<BarcodeScanner visible onScan={jest.fn()} onClose={jest.fn()} />);

    // The component must ask for permission exactly once on open.
    expect(Camera.requestCameraPermissionsAsync).toHaveBeenCalledTimes(1);

    // Granted -> camera viewfinder hint is shown.
    await waitFor(() => expect(screen.getByText('Point camera at a barcode')).toBeTruthy());
  });

  it('shows the permission-required message when the user denies access', async () => {
    (Camera.requestCameraPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'denied' });

    render(<BarcodeScanner visible onScan={jest.fn()} onClose={jest.fn()} />);

    await waitFor(() =>
      expect(screen.getByText('Camera permission required')).toBeTruthy(),
    );
    // Must not try to mount the camera when denied.
    expect(screen.queryByText('Point camera at a barcode')).toBeNull();
  });

  it('renders nothing when not visible', () => {
    const { queryByText } = render(
      <BarcodeScanner visible={false} onScan={jest.fn()} onClose={jest.fn()} />,
    );
    expect(queryByText('Camera permission required')).toBeNull();
    expect(queryByText('Point camera at a barcode')).toBeNull();
    expect(Camera.requestCameraPermissionsAsync).not.toHaveBeenCalled();
  });
});
