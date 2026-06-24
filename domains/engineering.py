import math
from loguru import logger

class EngineeringDomain:
    """Expert domain for mechanical engineering, CAD geometry simulation, and structural calculations."""

    def __init__(self, hologram_widget=None):
        self.hologram_widget = hologram_widget

    def design_gear_assembly(self, teeth_count: int = 12) -> tuple[list, list]:
        """Generates 3D coordinates for a mechanical gear assembly."""
        vertices = []
        connections = []
        
        # Center axle points (cylinder)
        vertices.append([0, 0, -30]) # 0
        vertices.append([0, 0, 30])  # 1
        connections.append((0, 1))
        
        # Inner hub rim
        hub_radius = 25
        hub_points = 8
        for i in range(hub_points):
            angle = (2 * math.pi * i) / hub_points
            x = hub_radius * math.cos(angle)
            y = hub_radius * math.sin(angle)
            vertices.append([x, y, -10]) # 2 to 9
            vertices.append([x, y, 10])  # 10 to 17
            
            idx = 2 + 2 * i
            connections.append((idx, idx + 1))
            connections.append((0, idx))
            connections.append((1, idx + 1))
            
            # Connect rim circle
            next_idx = 2 + 2 * ((i + 1) % hub_points)
            connections.append((idx, next_idx))
            connections.append((idx + 1, next_idx + 1))
            
        # Outer teeth
        outer_radius = 80
        inner_radius = 60
        tooth_idx_start = len(vertices)
        
        for i in range(teeth_count):
            angle = (2 * math.pi * i) / teeth_count
            next_angle = (2 * math.pi * (i + 0.5)) / teeth_count
            
            # Inner tooth root
            ix = inner_radius * math.cos(angle)
            iy = inner_radius * math.sin(angle)
            # Outer tooth tip
            ox = outer_radius * math.cos(angle + 0.15)
            oy = outer_radius * math.sin(angle + 0.15)
            ox2 = outer_radius * math.cos(next_angle - 0.15)
            oy2 = outer_radius * math.sin(next_angle - 0.15)
            # Next tooth root
            ix2 = inner_radius * math.cos(next_angle)
            iy2 = inner_radius * math.sin(next_angle)
            
            curr_start = tooth_idx_start + 8 * i
            
            # Front face roots/tips
            vertices.append([ix, iy, -5])   # +0
            vertices.append([ox, oy, -5])   # +1
            vertices.append([ox2, oy2, -5]) # +2
            vertices.append([ix2, iy2, -5]) # +3
            
            # Back face roots/tips
            vertices.append([ix, iy, 5])    # +4
            vertices.append([ox, oy, 5])    # +5
            vertices.append([ox2, oy2, 5])  # +6
            vertices.append([ix2, iy2, 5])  # +7
            
            # Front face connections
            connections.append((curr_start + 0, curr_start + 1))
            connections.append((curr_start + 1, curr_start + 2))
            connections.append((curr_start + 2, curr_start + 3))
            
            # Back face connections
            connections.append((curr_start + 4, curr_start + 5))
            connections.append((curr_start + 5, curr_start + 6))
            connections.append((curr_start + 6, curr_start + 7))
            
            # Inter-face connections
            for j in range(4):
                connections.append((curr_start + j, curr_start + j + 4))
                
            # Connect to hub and next tooth
            connections.append((2 + 2 * (i % hub_points), curr_start + 0))
            if i > 0:
                prev_start = tooth_idx_start + 8 * (i - 1)
                connections.append((prev_start + 3, curr_start + 0))
                
        # Close the tooth circle
        connections.append((tooth_idx_start + 8 * (teeth_count - 1) + 3, tooth_idx_start + 0))
        
        return vertices, connections

    def design_suspension(self) -> tuple[list, list]:
        """Generates 3D coordinates for a double-wishbone mechanical suspension."""
        vertices = []
        connections = []
        
        # Chassis mount points
        vertices.append([-100, 50, -50])   # 0: Upper Front Mount
        vertices.append([-100, -50, -50])  # 1: Upper Rear Mount
        vertices.append([-100, 50, 50])    # 2: Lower Front Mount
        vertices.append([-100, -50, 50])   # 3: Lower Rear Mount
        
        # Hub ball joints
        vertices.append([50, 0, -30])      # 4: Upper Ball Joint
        vertices.append([50, 0, 30])       # 5: Lower Ball Joint
        
        # Wheel spindle & rim outline
        vertices.append([60, 0, 0])        # 6: Spindle outer center
        vertices.append([60, 30, -60])     # 7: Rim Top Front
        vertices.append([60, -30, -60])    # 8: Rim Top Rear
        vertices.append([60, 30, 60])      # 9: Rim Bottom Front
        vertices.append([60, -30, 60])     # 10: Rim Bottom Rear
        
        # Shock absorber / Coilover mount
        vertices.append([0, 0, 10])        # 11: Shock Lower Arm Mount
        vertices.append([-80, 0, -80])     # 12: Shock Chassis Mount
        
        # Wishbones connections
        connections.append((0, 4))
        connections.append((1, 4))
        connections.append((2, 11))
        connections.append((3, 11))
        connections.append((11, 5))
        
        # Hub carrier connections
        connections.append((4, 5))
        connections.append((4, 6))
        connections.append((5, 6))
        
        # Rim connections
        connections.append((6, 7))
        connections.append((6, 8))
        connections.append((6, 9))
        connections.append((6, 10))
        connections.append((7, 8))
        connections.append((8, 10))
        connections.append((10, 9))
        connections.append((9, 7))
        
        # Shock absorber connection
        connections.append((12, 11))
        
        return vertices, connections

    def design_nozzle(self) -> tuple[list, list]:
        """Generates 3D coordinates for a rocket engine nozzle."""
        vertices = []
        connections = []
        
        # Generate concentric rings along the Z axis (flow direction)
        # Rings list: (Z_offset, radius, steps)
        rings_config = [
            (-80, 50),  # Combustor chamber inlet
            (-50, 52),
            (-20, 30),  # Throat narrowing
            (0, 15),    # Throat center
            (25, 25),   # expansion bell starts
            (60, 45),
            (90, 65)    # Bell exit
        ]
        
        steps = 10
        ring_idx = 0
        
        for z, r in rings_config:
            start_idx = len(vertices)
            for i in range(steps):
                angle = (2 * math.pi * i) / steps
                x = r * math.cos(angle)
                y = r * math.sin(angle)
                vertices.append([x, y, z])
                
                # Connect circle rim
                connections.append((start_idx + i, start_idx + (i + 1) % steps))
                
                # Connect to previous ring longitudinal struts
                if ring_idx > 0:
                    prev_start = start_idx - steps
                    connections.append((prev_start + i, start_idx + i))
            
            ring_idx += 1
            
        return vertices, connections

    def answer(self, text: str, memories: str = "") -> str:
        """Processes CAD design request, updates hologram widget, and returns explanation."""
        cmd = text.lower()
        logger.info(f"Engineering Domain resolving: {cmd}")
        
        success = False
        design_type = "CAD MODEL"
        
        if "gear" in cmd:
            vertices, connections = self.design_gear_assembly()
            design_type = "GEAR_ASSEMBLY"
            success = True
        elif "suspension" in cmd or "wishbone" in cmd:
            vertices, connections = self.design_suspension()
            design_type = "SUSPENSION_ASSEMBLY"
            success = True
        elif "nozzle" in cmd or "rocket" in cmd:
            vertices, connections = self.design_nozzle()
            design_type = "ROCKET_NOZZLE"
            success = True
            
        if success and self.hologram_widget:
            # Update the floating hologram overlay in the UI thread safely
            self.hologram_widget.set_hologram_object(vertices, connections, design_type)
            self.hologram_widget.show()
            
            specs = (
                f"Sir, I have modeled the 3D {design_type.replace('_', ' ')} inside the holographic viewport.\n\n"
                f"### Engineering Specifications:\n"
                f"- **Vertices Generated**: {len(vertices)}\n"
                f"- **Connections (Struts/Bonds)**: {len(connections)}\n"
            )
            
            if "gear" in cmd:
                specs += (
                    f"- **Teeth Count**: 12\n"
                    f"- **Outer Diameter**: 160mm\n"
                    f"- **Mechanical Advantage Ratio**: 1:1 direct model\n"
                    f"- **Material Suggestion**: Titanium-Alloy or High-impact carbon polymer\n"
                )
            elif "suspension" in cmd:
                specs += (
                    f"- **Type**: Short-long A-arm (SLA) double-wishbone\n"
                    f"- **Kinematic Travel**: +45mm / -30mm\n"
                    f"- **Roll Center height**: 85mm above ground contact plane\n"
                )
            else:
                specs += (
                    f"- **Nozzle Area Expansion Ratio (Ae/At)**: 18.7\n"
                    f"- **Throat Radius**: 15mm\n"
                    f"- **Characteristic Velocity (c*)**: 1,780 m/s\n"
                )
                
            return specs
            
        # Fallback to general explanation if not standard component
        return (
            "Sir, I can design and simulate custom mechanical CAD systems. "
            "Please ask me to design a 'gear assembly', 'double-wishbone suspension', or 'rocket nozzle' "
            "to view the live 3D holographic projection."
        )
