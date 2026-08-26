import React from "react";
import { View, StyleSheet } from "react-native";
import { semantic, palette } from "../../theme";

/**
 * PantryMotif — a hand-coded, warm-pantry SVG illustration used for empty
 * states, celebrations, and first-run moments.
 *
 * Implemented with plain React Native primitives so it requires no external
 * SVG dependency. The motif is a friendly pantry shelf with a jar, a bowl,
 * and a hanging herb bundle, rendered with simple rounded shapes.
 */
export function PantryMotif({ size = 144 }: { size?: number }) {
  const scale = size / 144;
  return (
    <View style={[styles.wrap, { width: size, height: size, borderRadius: size / 2 }]}>
      <View style={[
        styles.shelf,
        {
          width: 100 * scale,
          height: 8 * scale,
          top: 84 * scale,
          left: 22 * scale,
          borderRadius: 4 * scale,
        },
      ]}>
        <View style={[styles.leg, { left: 8 * scale, height: 36 * scale }]} />
        <View style={[styles.leg, { right: 8 * scale, height: 36 * scale }]} />
      </View>

      {/* Jar */}
      <View style={[
        styles.jar,
        {
          width: 30 * scale,
          height: 38 * scale,
          left: 30 * scale,
          top: 48 * scale,
          borderRadius: 6 * scale,
        },
      ]}>
        <View style={[styles.jarLid, {
          width: 30 * scale,
          height: 7 * scale,
          borderTopLeftRadius: 5 * scale,
          borderTopRightRadius: 5 * scale,
        }]} />
      </View>

      {/* Bowl */}
      <View style={[
        styles.bowl,
        {
          width: 38 * scale,
          height: 22 * scale,
          left: 68 * scale,
          top: 64 * scale,
          borderBottomLeftRadius: 18 * scale,
          borderBottomRightRadius: 18 * scale,
        },
      ]}>
        <View style={[styles.bowlRim, {
          width: 38 * scale,
          height: 4 * scale,
          borderRadius: 2 * scale,
        }]} />
      </View>

      {/* Herb bundle hanging above */}
      <View style={[styles.string, {
        width: 2 * scale,
        height: 28 * scale,
        left: 96 * scale,
        top: 24 * scale,
      }]} />
      <View style={[styles.herbLeaf, {
        width: 12 * scale,
        height: 20 * scale,
        left: 90 * scale,
        top: 50 * scale,
        borderRadius: 10 * scale,
      }]} />
      <View style={[styles.herbLeaf, {
        width: 10 * scale,
        height: 16 * scale,
        left: 98 * scale,
        top: 52 * scale,
        borderRadius: 8 * scale,
      }]} />

      {/* Sun/glow dot */}
      <View style={[styles.sun, {
        width: 12 * scale,
        height: 12 * scale,
        left: 34 * scale,
        top: 28 * scale,
        borderRadius: 6 * scale,
      }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: semantic.surfaceElevated,
    borderWidth: 1,
    borderColor: semantic.border,
    justifyContent: "center",
    alignItems: "center",
    overflow: "hidden",
  },
  shelf: {
    position: "absolute",
    backgroundColor: palette.espresso[400],
    justifyContent: "flex-end",
    flexDirection: "row",
  },
  leg: {
    position: "absolute",
    bottom: 0,
    width: 4,
    backgroundColor: palette.espresso[400],
    borderBottomLeftRadius: 2,
    borderBottomRightRadius: 2,
  },
  jar: {
    position: "absolute",
    backgroundColor: palette.amber[100],
    borderWidth: 2,
    borderColor: palette.amber[400],
    justifyContent: "flex-start",
  },
  jarLid: {
    backgroundColor: palette.terracotta[400],
  },
  bowl: {
    position: "absolute",
    backgroundColor: palette.terracotta[100],
    borderWidth: 2,
    borderColor: palette.terracotta[300],
    borderTopWidth: 0,
    justifyContent: "flex-start",
  },
  bowlRim: {
    backgroundColor: palette.terracotta[300],
  },
  string: {
    position: "absolute",
    backgroundColor: palette.espresso[400],
  },
  herbLeaf: {
    position: "absolute",
    backgroundColor: palette.green[200],
    borderWidth: 1,
    borderColor: palette.green[400],
  },
  sun: {
    position: "absolute",
    backgroundColor: palette.amber[300],
  },
});
