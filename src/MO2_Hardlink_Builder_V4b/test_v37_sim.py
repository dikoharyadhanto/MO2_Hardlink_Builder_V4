import unittest
from model.state import LayeredManifest
from model.engines.state_manager import OwnerStackManager

class TestV37Architecture(unittest.TestCase):
    def setUp(self):
        self.manifest = LayeredManifest()
        # Mocking Layer A data
        self.manifest.mod_index = {
            "Mod_Base": {"files": {"textures/armor.dds": {"source": "C:/Mod_Base/armor.dds"}}},
            "Mod_HD": {"files": {"textures/armor.dds": {"source": "C:/Mod_HD/armor.dds"}}},
            "Mod_4K": {"files": {"textures/armor.dds": {"source": "C:/Mod_4K/armor.dds"}}}
        }
        # Initial Load Order: Base (0) < HD (1) < 4K (2)
        self.load_order = {"Mod_Base": 0, "Mod_HD": 1, "Mod_4K": 2}
        self.manager = OwnerStackManager(self.manifest, self.load_order)

    def test_t1_pop_fallback(self):
        # Push owners
        self.manager.push_owner("textures/armor.dds", "Mod_Base")
        self.manager.push_owner("textures/armor.dds", "Mod_HD")
        self.manager.push_owner("textures/armor.dds", "Mod_4K")
        
        # Verify initial stack
        stack = self.manifest.path_owners["textures/armor.dds"]
        self.assertEqual(stack, ["Mod_4K", "Mod_HD", "Mod_Base"])
        self.assertEqual(self.manifest.active_owner("textures/armor.dds"), "Mod_4K")
        
        # Simulate disabling the highest priority mod (T1)
        new_owner = self.manager.pop_owner("textures/armor.dds", "Mod_4K")
        
        # Verify fallback is O(1) and correct
        self.assertEqual(new_owner, "Mod_HD")
        self.assertEqual(self.manifest.path_owners["textures/armor.dds"], ["Mod_HD", "Mod_Base"])
        self.assertEqual(self.manifest.active_owner("textures/armor.dds"), "Mod_HD")
        
        # Verify Invariant
        violations = self.manager.verify_invariant()
        self.assertEqual(len(violations), 0)

    def test_t3_explicit_load_order_shift(self):
        # Setup initial state
        self.manager.push_owner("textures/armor.dds", "Mod_Base")
        self.manager.push_owner("textures/armor.dds", "Mod_HD")
        
        self.assertEqual(self.manifest.active_owner("textures/armor.dds"), "Mod_HD")
        
        # T3: Shift load order so Base is higher priority than HD
        # New Load Order: HD (0) < Base (1)
        new_load_order = ["Mod_HD", "Mod_Base", "Mod_4K"]
        self.manifest.full_recompute_layer_b(new_load_order)
        
        # Verify the stack is rebuilt correctly
        stack = self.manifest.path_owners["textures/armor.dds"]
        self.assertEqual(stack, ["Mod_4K", "Mod_Base", "Mod_HD"])
        self.assertEqual(self.manifest.active_owner("textures/armor.dds"), "Mod_4K")

    def test_t4_action_queue_idempotency(self):
        # Setup new state
        self.manager.push_owner("textures/armor.dds", "Mod_4K")
        
        # T4: Compute action queue without old manifest (Fresh build)
        queue1 = self.manifest.compute_action_queue(None)
        
        # Should contain 1 LINK operation
        self.assertEqual(len(queue1), 1)
        self.assertEqual(queue1[0][0], "LINK")
        self.assertEqual(queue1[0][1], "textures/armor.dds")
        
        # Simulate computing action queue again with identical state
        queue2 = self.manifest.compute_action_queue(self.manifest)
        
        # Should be empty since there are no differences
        self.assertEqual(len(queue2), 0)

    def test_hotfix_priority_corruption_prevention(self):
        # Attempting to push a mod that is not in the load order dict should raise KeyError
        with self.assertRaises(KeyError):
            self.manager.push_owner("textures/armor.dds", "Mod_Unknown")

if __name__ == '__main__':
    unittest.main()
