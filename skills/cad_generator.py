import math
from loguru import logger

class CADGenerator:
    """Generates 3D wireframe coordinate meshes based on conversational design prompts."""

    def generate_mesh(self, prompt: str) -> tuple[list, list, str, list]:
        """
        Parses the design query and returns (vertices, connections, name, labels).
        """
        p = prompt.lower().strip()
        logger.info(f"CAD Generator: Designing 3D wireframe for '{p}'")

        if "arc reactor" in p:
            return self._build_arc_reactor()
        elif "gear" in p or "gearbox" in p:
            return self._build_planetary_gearbox()
        elif "dna" in p or "helix" in p:
            return self._build_dna_double_helix()
        elif "sphere" in p or "globe" in p:
            return self._build_wireframe_sphere()
        else:
            # Fallback to a futuristic Stark element (Vibranium Core)
            return self._build_vibranium_core()

    def _build_arc_reactor(self) -> tuple[list, list, str, list]:
        vertices = [[0.0, 0.0, 0.0]]  # Center palladium core (0)
        labels = ["Palladium Core"]
        connections = []

        # Inner ring: 10 vertices
        num_segments = 10
        inner_r = 50.0
        for i in range(num_segments):
            angle = (2.0 * math.pi / num_segments) * i
            x = inner_r * math.cos(angle)
            y = inner_r * math.sin(angle)
            z = 0.0
            vertices.append([x, y, z])
            labels.append(f"Inner Node {i+1}")
            # Connect to core
            connections.append((0, len(vertices) - 1))
            # Ring connections
            if i > 0:
                connections.append((len(vertices) - 2, len(vertices) - 1))
        # Loop inner ring closure
        connections.append((1, len(vertices) - 1))

        # Outer ring: 10 vertices
        outer_r = 90.0
        start_idx = len(vertices)
        for i in range(num_segments):
            angle = (2.0 * math.pi / num_segments) * i
            x = outer_r * math.cos(angle)
            y = outer_r * math.sin(angle)
            z = -15.0 if i % 2 == 0 else 15.0  # Alternating depth to make it 3D
            vertices.append([x, y, z])
            labels.append(f"Coil Segment {i+1}")
            # Connect to inner ring corresponding node
            connections.append((i + 1, start_idx + i))
            # Outer ring connections
            if i > 0:
                connections.append((start_idx + i - 1, start_idx + i))
        # Loop outer ring closure
        connections.append((start_idx, len(vertices) - 1))

        return vertices, connections, "ARC REACTOR CORE", labels

    def _build_planetary_gearbox(self) -> tuple[list, list, str, list]:
        vertices = [[0.0, 0.0, 0.0]]  # Sun gear center (0)
        labels = ["Sun Gear"]
        connections = []

        # Sun gear teeth nodes
        num_teeth = 8
        sun_r = 30.0
        for i in range(num_teeth):
            angle = (2.0 * math.pi / num_teeth) * i
            r = sun_r + (10.0 if i % 2 == 0 else 0.0)
            x = r * math.cos(angle)
            y = r * math.sin(angle)
            vertices.append([x, y, 0.0])
            labels.append(f"Sun Tooth {i+1}")
            connections.append((0, len(vertices) - 1))
            if i > 0:
                connections.append((len(vertices) - 2, len(vertices) - 1))
        connections.append((1, len(vertices) - 1))

        # 3 Planets revolving around
        num_planets = 3
        planet_orbit_r = 75.0
        planet_r = 20.0
        for p_idx in range(num_planets):
            p_angle = (2.0 * math.pi / num_planets) * p_idx
            px = planet_orbit_r * math.cos(p_angle)
            py = planet_orbit_r * math.sin(p_angle)
            
            planet_center_idx = len(vertices)
            vertices.append([px, py, 0.0])
            labels.append(f"Planet {p_idx+1} Center")
            # Connect planet center to sun center (carrier frame)
            connections.append((0, planet_center_idx))
            
            # Planet teeth
            for i in range(6):
                angle = (2.0 * math.pi / 6) * i
                r = planet_r + (6.0 if i % 2 == 0 else 0.0)
                tx = px + r * math.cos(angle)
                ty = py + r * math.sin(angle)
                vertices.append([tx, ty, 5.0 if i % 2 == 0 else -5.0])
                labels.append(f"Planet {p_idx+1} Tooth {i+1}")
                connections.append((planet_center_idx, len(vertices) - 1))
                if i > 0:
                    connections.append((len(vertices) - 2, len(vertices) - 1))
            connections.append((planet_center_idx + 1, len(vertices) - 1))

        return vertices, connections, "PLANETARY GEARBOX", labels

    def _build_dna_double_helix(self) -> tuple[list, list, str, list]:
        vertices = []
        labels = []
        connections = []

        num_rungs = 12
        spacing = 18.0
        radius = 40.0
        twist = 0.5  # radians per rung

        # Construct Strand A and Strand B
        for i in range(num_rungs):
            z = -100.0 + i * spacing
            angle_a = i * twist
            angle_b = angle_a + math.pi  # opposite side

            xa = radius * math.cos(angle_a)
            ya = radius * math.sin(angle_a)
            vertices.append([xa, ya, z])
            labels.append(f"Strand A - Base {i+1}")
            idx_a = len(vertices) - 1

            xb = radius * math.cos(angle_b)
            yb = radius * math.sin(angle_b)
            vertices.append([xb, yb, z])
            labels.append(f"Strand B - Base {i+1}")
            idx_b = len(vertices) - 1

            # Connect A to B (Rung connection)
            connections.append((idx_a, idx_b))

            # Connect along backbones
            if i > 0:
                connections.append((idx_a - 2, idx_a))
                connections.append((idx_b - 2, idx_b))

        return vertices, connections, "DNA DOUBLE HELIX", labels

    def _build_wireframe_sphere(self) -> tuple[list, list, str, list]:
        vertices = []
        labels = []
        connections = []

        # Latitudinal/Longitudinal mesh
        radius = 70.0
        rings = 4
        sectors = 8

        # Pole points
        vertices.append([0.0, 0.0, radius])
        labels.append("North Pole")
        north_idx = 0

        vertices.append([0.0, 0.0, -radius])
        labels.append("South Pole")
        south_idx = 1

        # Intermediate rings
        for r in range(1, rings):
            phi = math.pi * r / rings
            z = radius * math.cos(phi)
            ring_r = radius * math.sin(phi)
            start_ring_idx = len(vertices)

            for s in range(sectors):
                theta = 2.0 * math.pi * s / sectors
                x = ring_r * math.cos(theta)
                y = ring_r * math.sin(theta)
                vertices.append([x, y, z])
                labels.append(f"Ring {r} Node {s+1}")
                curr_idx = len(vertices) - 1

                # Connect ring nodes horizontally
                if s > 0:
                    connections.append((curr_idx - 1, curr_idx))
                
                # Connect vertically
                if r == 1:
                    # Connect to North Pole
                    connections.append((north_idx, curr_idx))
                else:
                    # Connect to previous ring node
                    prev_ring_node = curr_idx - sectors
                    connections.append((prev_ring_node, curr_idx))

            # Close horizontal ring
            connections.append((start_ring_idx, len(vertices) - 1))

        # Connect last ring to South Pole
        last_ring_start = len(vertices) - sectors
        for s in range(sectors):
            connections.append((south_idx, last_ring_start + s))

        return vertices, connections, "SPHERICAL TARGET VECTOR", labels

    def _build_vibranium_core(self) -> tuple[list, list, str, list]:
        # Dodecahedron shape representing custom heavy element
        vertices = [
            [0, 0, 80],
            [50, 0, 30], [-25, 43, 30], [-25, -43, 30],
            [25, 43, -30], [-50, 0, -30], [25, -43, -30],
            [0, 0, -80]
        ]
        labels = [
            "Upper Gateway",
            "Coil A1", "Coil A2", "Coil A3",
            "Coil B1", "Coil B2", "Coil B3",
            "Lower Gateway"
        ]
        connections = [
            (0, 1), (0, 2), (0, 3),
            (1, 4), (1, 6), (2, 4), (2, 5), (3, 5), (3, 6),
            (7, 4), (7, 5), (7, 6)
        ]
        return vertices, connections, "VIBRANIUM SYNTHETIC CORE", labels
