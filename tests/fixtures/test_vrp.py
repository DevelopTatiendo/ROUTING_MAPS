"""
Test Suite para VRP F1 System
Tests unitarios y fixtures para todos los módulos
"""
import unittest
import pandas as pd
import numpy as np
import os
import json
import tempfile
from unittest.mock import patch, MagicMock
import sys
import warnings

# Agregar directorio raíz al path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Imports del sistema VRP F1
try:
    from pre_procesamiento.prepro_ruteo import build_scenario
    from vrp.utils.cache import obj_hash, load_cache, save_cache, clear_old_cache
    from vrp.matrix.osrm import compute_matrix, test_osrm_connection
    from vrp.solver.or_tools_openvrp import solve_open_vrp
    from vrp.paths.osrm_route import route_polyline, batch_route_polylines
    from vrp.export.writers import (
        export_routes_csv, export_routes_geojson, 
        build_map_with_antpaths, export_summary_report
    )
    VRP_MODULES_AVAILABLE = True
except ImportError as e:
    VRP_MODULES_AVAILABLE = False
    warnings.warn(f"VRP modules not available: {e}")


class TestDataFixtures:
    """
    Fixtures de datos de prueba para tests.
    """
    
    @staticmethod
    def sample_stops_df():
        """
        DataFrame de stops de prueba.
        """
        return pd.DataFrame([
            {
                'id_contacto': 'S_001',
                'lat': 3.4516,
                'lon': -76.5320,
                'nombre': 'Cliente Norte',
                'prioridad': 3,
                'zona': 'Norte',
                'duracion_min': 10
            },
            {
                'id_contacto': 'S_002', 
                'lat': 3.4526,
                'lon': -76.5330,
                'nombre': 'Cliente Centro',
                'prioridad': 2,
                'zona': 'Centro',
                'duracion_min': 15
            },
            {
                'id_contacto': 'S_003',
                'lat': 3.4536,
                'lon': -76.5340,
                'nombre': 'Cliente Sur',
                'prioridad': 4,
                'zona': 'Sur',
                'duracion_min': 8
            },
            {
                'id_contacto': 'S_004',
                'lat': 3.4546,
                'lon': -76.5350,
                'nombre': 'Cliente Este',
                'prioridad': 1,
                'zona': 'Este',
                'duracion_min': 12
            }
        ])
    
    @staticmethod
    def sample_vehicles_df():
        """
        DataFrame de vehicles de prueba.
        """
        return pd.DataFrame([
            {
                'id_vehiculo': 'V1',
                'start_lat': 3.4500,
                'start_lon': -76.5300,
                'end_lat': 3.4500,
                'end_lon': -76.5300,
                'max_stops': 40,
                'tw_start': '08:00',
                'tw_end': '18:00',
                'break_start': '12:00',
                'break_end': '13:00'
            },
            {
                'id_vehiculo': 'V2',
                'start_lat': 3.4510,
                'start_lon': -76.5310,
                'end_lat': 3.4510,
                'end_lon': -76.5310,
                'max_stops': 35,
                'tw_start': '09:00',
                'tw_end': '17:00',
                'break_start': '12:30',
                'break_end': '13:30'
            }
        ])
    
    @staticmethod
    def sample_scenario():
        """
        Scenario completo de prueba.
        """
        stops_df = TestDataFixtures.sample_stops_df()
        vehicles_df = TestDataFixtures.sample_vehicles_df()
        
        return {
            'stops': stops_df.to_dict('records'),
            'vehicles': vehicles_df.to_dict('records'),
            'rules': {
                'max_stops_per_vehicle': 40,
                'balance_load': True,
                'free_start': True,
                'return_to_start': False,
                'cost_weights': {'time': 0.7, 'distance': 0.3}
            },
            'start_id': None
        }


@unittest.skipUnless(VRP_MODULES_AVAILABLE, "VRP modules not available")
class TestVRPF1Basic(unittest.TestCase):
    """
    Tests básicos del sistema VRP F1
    """
    
    def test_build_scenario_basic(self):
        """Test básico de build_scenario"""
        stops_df = TestDataFixtures.sample_stops_df()
        vehicles_df = TestDataFixtures.sample_vehicles_df()
        
        scenario = build_scenario(
            shortlist_csv=stops_df,
            vehicles_csv=vehicles_df,
            max_stops_per_vehicle=40
        )
        
        # Verificar estructura
        self.assertIn('stops', scenario)
        self.assertIn('vehicles', scenario) 
        self.assertIn('rules', scenario)
        
        # Verificar contenido
        self.assertEqual(len(scenario['stops']), 4)
        self.assertEqual(len(scenario['vehicles']), 2)
        self.assertEqual(scenario['rules']['max_stops_per_vehicle'], 40)
    
    def test_obj_hash_consistency(self):
        """Test consistencia de hashing"""
        obj1 = {'a': 1, 'b': [2, 3]}
        obj2 = {'a': 1, 'b': [2, 3]}  # Idéntico
        obj3 = {'a': 1, 'b': [2, 4]}  # Diferente
        
        hash1 = obj_hash(obj1)
        hash2 = obj_hash(obj2)
        hash3 = obj_hash(obj3)
        
        self.assertEqual(hash1, hash2)  # Iguales
        self.assertNotEqual(hash1, hash3)  # Diferentes


class VRPTestSuite:
    """
    Suite básica de tests VRP F1
    """
    
    @staticmethod 
    def run_quick_smoke_test():
        """
        Ejecuta test rápido de smoke para verificar funcionalidad básica.
        """
        print("🔥 Ejecutando Smoke Test VRP F1...")
        
        if not VRP_MODULES_AVAILABLE:
            print("❌ VRP modules no disponibles")
            return False
        
        try:
            # Test 1: Fixtures básicas
            stops_df = TestDataFixtures.sample_stops_df()
            vehicles_df = TestDataFixtures.sample_vehicles_df()
            scenario = TestDataFixtures.sample_scenario()
            
            print("✅ Fixtures básicas OK")
            
            # Test 2: Build scenario
            built_scenario = build_scenario(stops_df, vehicles_df, max_stops_per_vehicle=40)
            assert len(built_scenario['stops']) > 0
            print("✅ Build scenario OK")
            
            # Test 3: Cache system
            test_obj = {'test': 'data'}
            hash_result = obj_hash(test_obj)
            assert len(hash_result) > 0
            print("✅ Cache system OK")
            
            # Test 4: Matrix computation (fallback)
            with patch('vrp.matrix.osrm.requests.get', side_effect=ConnectionError()):
                matrix_result = compute_matrix(scenario['stops'], "http://mock:5001")
                assert matrix_result['success']
                assert matrix_result['method'] == 'haversine_fallback'
            print("✅ Matrix computation (fallback) OK")
            
            print("🎉 Smoke test exitoso!")
            return True
            
        except Exception as e:
            print(f"❌ Smoke test falló: {e}")
            return False
            
        if df_export is not None:
            print(f"✅ DataFrame export con {len(df_export)} filas")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="VRP F1 Test Suite")
    parser.add_argument("--mode", choices=["full", "smoke"], default="smoke",
                       help="Modo de ejecución de tests")
    parser.add_argument("--verbose", action="store_true", 
                       help="Output detallado")
    
    args = parser.parse_args()
    
    if args.mode == "smoke":
        success = VRPTestSuite.run_quick_smoke_test()
        sys.exit(0 if success else 1)
    else:
        # Ejecutar tests unitarios básicos
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(TestVRPF1Basic)
        runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
        result = runner.run(suite)
        success = len(result.failures) == 0 and len(result.errors) == 0
        sys.exit(0 if success else 1)