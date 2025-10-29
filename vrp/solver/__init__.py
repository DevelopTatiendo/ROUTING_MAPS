"""
Solver Module for VRP System
OR-Tools based optimization with advanced constraints
"""

from .ortools_solver import ORToolsVRPSolver, VRPSolution

__all__ = [
    'ORToolsVRPSolver',
    'VRPSolution'
]