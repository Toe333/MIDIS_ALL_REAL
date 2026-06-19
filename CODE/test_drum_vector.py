#!/usr/bin/env python3
"""
CODE/test_drum_vector.py — Unit tests for DrumDNA extraction.
Verifies musical truths and dimensional invariants of CODE/31_drum_vector.py.
"""
import os, sys
import numpy as np
import unittest
import importlib

# Add current dir to path to import 31_drum_vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
drum_module = importlib.import_module("31_drum_vector")
drum_of = drum_module.drum_of
DIMS = drum_module.DIMS

class TestDrumDNA(unittest.TestCase):

    def make_midi(self, notes, tpb=480, chan=9):
        if not notes: return None
        arr = []
        for t, p, v in notes:
            arr.append([t * tpb, tpb * 0.25, chan, p, v])
        return np.array(arr, dtype=np.float64)

    def test_empty(self):
        has_drums, f = drum_of(None, 480)
        self.assertEqual(has_drums, 0)
        self.assertTrue(all(f[d] == 0.0 for d in DIMS))
        
        has_drums, f = drum_of(self.make_midi([], chan=0), 480)
        self.assertEqual(has_drums, 0)
        self.assertTrue(all(f[d] == 0.0 for d in DIMS))

    def test_melodic_only(self):
        notes = [(0.0, 60, 100), (1.0, 62, 100)]
        has_drums, f = drum_of(self.make_midi(notes, chan=0), 480)
        self.assertEqual(has_drums, 0)
        self.assertTrue(all(f[d] == 0.0 for d in DIMS))

    def test_rock_backbeat(self):
        notes = [
            (0.0, 36, 100), (1.0, 38, 100), (2.0, 36, 100), (3.0, 38, 100),
        ]
        has_drums, f = drum_of(self.make_midi(notes), 480)
        self.assertEqual(has_drums, 1)
        self.assertEqual(f['kick_density'], 2.0)
        self.assertEqual(f['snare_density'], 2.0)
        self.assertEqual(f['snare_backbeat'], 1.0)
        self.assertEqual(f['kick_on_downbeat'], 0.5)
        # Grid is a probability distribution (sums to 1 per voice)
        self.assertEqual(f['kick_g00'], 0.5)
        self.assertEqual(f['kick_g08'], 0.5)
        self.assertEqual(f['snare_g04'], 0.5)
        self.assertEqual(f['snare_g12'], 0.5)

    def test_one_drop(self):
        notes = [(2.0, 36, 100), (2.0, 38, 100)]
        has_drums, f = drum_of(self.make_midi(notes), 480)
        self.assertEqual(has_drums, 1)
        self.assertGreater(f['beat3_accent'], 0.9)
        self.assertEqual(f['beat1_accent'], 0.0)
        self.assertEqual(f['snare_backbeat'], 0.0)

    def test_swing(self):
        straight = [(i * 0.5, 42, 100) for i in range(8)]
        _, f_s = drum_of(self.make_midi(straight), 480)
        swung = []
        for i in range(4):
            swung.append((float(i), 42, 100))
            swung.append((i + 0.66, 42, 100))
        _, f_w = drum_of(self.make_midi(swung), 480)
        self.assertLess(f_s['swing'], 0.1)
        self.assertGreater(f_w['swing'], 0.2)

    def test_laidback(self):
        on_grid = [(float(i), 36, 100) for i in range(4)]
        _, f_on = drum_of(self.make_midi(on_grid), 480)
        self.assertAlmostEqual(f_on['laidback'], 0.5, delta=0.01)
        late = [(i + 0.05, 36, 100) for i in range(4)]
        _, f_late = drum_of(self.make_midi(late), 480)
        self.assertGreater(f_late['laidback'], 0.5)
        early = [(i - 0.05, 36, 100) for i in range(4)]
        _, f_early = drum_of(self.make_midi(early), 480)
        self.assertLess(f_early['laidback'], 0.5)

if __name__ == "__main__":
    unittest.main()
