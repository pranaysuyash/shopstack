import { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Modal, TouchableOpacity, Animated, Easing } from 'react-native';
import { CameraView, Camera, type CameraViewRef } from 'expo-camera';
import { semantic, spacing, typography, radius, z } from '../../theme';
import { lookupBarcode, type BarcodeProduct } from '../../api/barcode';

interface BarcodeScannerProps {
  visible: boolean;
  onScan: (product: BarcodeProduct) => void;
  onClose: () => void;
}

export function BarcodeScanner({ visible, onScan, onClose }: BarcodeScannerProps) {
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [scanning, setScanning] = useState(true);
  const [lookup, setLookup] = useState(false);
  const scanLineAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      (async () => {
        const { status } = await Camera.requestCameraPermissionsAsync();
        setHasPermission(status === 'granted');
      })();
      setScanning(true);
      setLookup(false);
      Animated.loop(
        Animated.sequence([
          Animated.timing(scanLineAnim, {
            toValue: 1,
            duration: 2500,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
          Animated.timing(scanLineAnim, {
            toValue: 0,
            duration: 2500,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
        ]),
      ).start();
    } else {
      scanLineAnim.stopAnimation();
    }
    return () => scanLineAnim.stopAnimation();
  }, [visible, scanLineAnim]);

  function handleBarCodeScanned(result: { data: string }) {
    if (!scanning) return;
    setScanning(false);
    setLookup(true);
    lookupBarcode(result.data)
      .then((product) => {
        if (product) {
          onScan(product);
        } else {
          onScan({
            code: result.data,
            name: `Barcode ${result.data}`,
            brand: '',
            category: '',
            quantity: '',
            imageUrl: '',
            nutriscore: '',
            nutritionPer100g: null,
          });
        }
      })
      .catch(() => {
        onScan({
          code: result.data,
          name: `Barcode ${result.data}`,
          brand: '',
          category: '',
          quantity: '',
          imageUrl: '',
          nutriscore: '',
          nutritionPer100g: null,
        });
      })
      .finally(() => {
        setLookup(false);
        onClose();
      });
  }

  if (!visible) return null;

  const translateY = scanLineAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 200],
  });

  return (
    <Modal visible={visible} animationType="slide" transparent={false}>
      <View style={styles.container}>
        {hasPermission === false ? (
          <View style={styles.permissionDenied}>
            <Text style={styles.permissionText}>Camera permission required</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeButton}>
              <Text style={styles.closeButtonText}>Close</Text>
            </TouchableOpacity>
          </View>
        ) : hasPermission === null ? (
          <View style={styles.permissionDenied}>
            <Text style={styles.permissionText}>Requesting camera permission...</Text>
          </View>
        ) : (
          <CameraView
            style={StyleSheet.absoluteFillObject}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128'] }}
            onBarcodeScanned={handleBarCodeScanned}
          >
            <View style={styles.overlay}>
              <View style={styles.viewfinder}>
                <Animated.View
                  style={[
                    styles.scanLine,
                    { transform: [{ translateY }] },
                  ]}
                />
              </View>
              <Text style={styles.hint}>
                {lookup ? 'Looking up product...' : 'Point camera at a barcode'}
              </Text>
              <TouchableOpacity onPress={onClose} style={styles.cancelButton}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </CameraView>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  permissionDenied: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: semantic.background,
    padding: spacing[8],
  },
  permissionText: {
    fontSize: typography.sizes.lg.size,
    color: semantic.textPrimary,
    textAlign: 'center',
    marginBottom: spacing[6],
  },
  overlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  viewfinder: {
    width: 250,
    height: 200,
    borderWidth: 2,
    borderColor: semantic.primary,
    borderRadius: radius.lg,
    overflow: 'hidden',
    backgroundColor: 'transparent',
  },
  scanLine: {
    width: '100%',
    height: 2,
    backgroundColor: '#fff',
  },
  hint: {
    marginTop: spacing[6],
    fontSize: typography.sizes.base.size,
    color: '#fff',
    textAlign: 'center',
  },
  cancelButton: {
    marginTop: spacing[8],
    paddingVertical: spacing[3],
    paddingHorizontal: spacing[8],
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: radius.full,
  },
  cancelText: {
    fontSize: typography.sizes.base.size,
    color: '#fff',
    fontWeight: typography.weight.semibold,
  },
  closeButton: {
    paddingVertical: spacing[3],
    paddingHorizontal: spacing[8],
    backgroundColor: semantic.primary,
    borderRadius: radius.md,
  },
  closeButtonText: {
    fontSize: typography.sizes.base.size,
    color: semantic.onPrimary,
    fontWeight: typography.weight.semibold,
  },
});
