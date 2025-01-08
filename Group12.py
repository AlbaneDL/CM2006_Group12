import vtk
import os
import sys
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QFrame, QGridLayout, QSizePolicy, QSlider,  QPushButton, QFileDialog, QInputDialog, QVBoxLayout, QGroupBox
from PyQt5.QtCore import Qt, QTimer
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

def choose_files():
    # selecting an image file
    image_file, _ = QFileDialog.getOpenFileName(None, "Choose Image File", "", "NIfTI Files (*.nii.gz);")
    if not image_file:
        print("No image file selected. Exiting.")
        sys.exit(1)  # Exit if no file is chosen

    # selecting a mask file
    mask_file, _ = QFileDialog.getOpenFileName(None, "Choose Mask File", "", "NIfTI Files (*.nii.gz);")
    if not mask_file:
        print("No mask file selected. Exiting.")
        sys.exit(1)  # Exit if no file is chosen

    # selecting a prosthesis file
    prosthesis_file, _ = QFileDialog.getOpenFileName(None, "Choose Prosthesis File", "", "STL Files (*.stl)")
    if not prosthesis_file:
        print("No prosthesis file selected. Exiting.")
        sys.exit(1)  # Exit if no file is chosen

    # Ask the user to specify the side (Right or Left)
    side, ok = QInputDialog.getItem(None, "Select Side", "Choose prosthesis side:", ["Right", "Left"], 0, False)
    if not ok:
        print("No side selected. Exiting.")
        sys.exit(1)  # Exit if no side is chosen

    return image_file, mask_file, prosthesis_file, side



# all this class is to visualize the multi planar view of the CT scan
class MPRVisualizer:
    def __init__(self, image_data, orientation, parent_widget):
        self.image_data = image_data
        self.orientation = orientation
        self.parent_widget = parent_widget

        # Configure slice plane
        self.reslice_axes = vtk.vtkMatrix4x4()
        self.reslice = vtk.vtkImageReslice()
        self.reslice.SetInputData(self.image_data)
        self.reslice.SetOutputDimensionality(2) # output dimension should be 2D
        self.reslice.SetInterpolationModeToLinear()

        # Configure window-level mapper
        # this window_level transforms raw image intensities (Hounsfield Units) into displayable grayscale or color values (mapped to 0-255)
        self.window_level = vtk.vtkImageMapToWindowLevelColors()
        self.window_level.SetInputConnection(self.reslice.GetOutputPort())
        self.window_level.SetWindow(2000) #Increase for wider intensity range (contrast)
        self.window_level.SetLevel(100) # specifies the center of the intensity range

        # image actor
        self.image_actor = vtk.vtkImageActor()
        self.image_actor.GetMapper().SetInputConnection(self.window_level.GetOutputPort())

        # Renderer setup
        self.renderer = vtk.vtkRenderer()
        self.renderer.AddActor(self.image_actor)
        self.renderer.SetBackground(0.0, 0.0, 0.0)

        # Create VTK widget for the MPR views and interactor
        self.widget = QVTKRenderWindowInteractor(self.parent_widget)
        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.widget.GetRenderWindow().AddRenderer(self.renderer)

        interactor = self.widget.GetRenderWindow().GetInteractor()
        interactor.SetInteractorStyle(vtk.vtkInteractorStyleImage())

        self.set_slice_orientation(self.orientation)
        self.set_initial_slice()
        self.widget.GetRenderWindow().Render()

        # set the parameter for the measurements
        self.distance_widget = None
        self.text_actor = None

    def set_slice_orientation(self, orientation): #define the reslice_axis based on the orientation
        self.reslice_axes.Identity()
        if orientation == "axial":
            self.reslice_axes.DeepCopy((1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1))
        elif orientation == "coronal":
            self.reslice_axes.DeepCopy((1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1))
        elif orientation == "sagittal":
            self.reslice_axes.DeepCopy((0, 0, -1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1))
        self.reslice.SetResliceAxes(self.reslice_axes)
        self.reslice.Update()

    def set_initial_slice(self): # define the initial slice to render in each MPR view: the middle one
        slicing_axis = {"axial": 2, "coronal": 1, "sagittal": 0}[self.orientation]
        origin = [0, 0, 0]
        origin[slicing_axis] = self.image_data.GetDimensions()[slicing_axis] // 2
        self.reslice.SetResliceAxesOrigin(*origin)
        self.reslice.Update()

    def create_slider(self): # slider for each MPR view to scroll over slices
        slicing_axis = {"axial": 2, "coronal": 1, "sagittal": 0}[self.orientation]
        max_slices = self.image_data.GetDimensions()[slicing_axis]

        slider = QSlider(Qt.Horizontal, self.parent_widget)
        slider.setMinimum(1) #from slice 1
        slider.setMaximum(max_slices) # to the maximum number of slices
        slider.setValue(max_slices // 2) # initial value of the slider

        slider.valueChanged.connect(self.update_slice) # update the slice based on the slider
        return slider

    def update_slice(self, value):  # update the slice based on the slider
        slicing_axis = {"axial": 2, "coronal": 1, "sagittal": 0}[self.orientation]
        origin = [0, 0, 0]
        origin[slicing_axis] = value - 1 
        self.reslice.SetResliceAxesOrigin(*origin)
        self.reslice.Update()
        self.widget.GetRenderWindow().Render()
    
    ### Measuring Distance in Pixels

    def toggle_distance_measurement(self):
        if not self.distance_widget:
            self.distance_widget = vtk.vtkDistanceWidget()
            self.distance_widget.SetInteractor(self.widget.GetRenderWindow().GetInteractor())
            self.distance_widget.CreateDefaultRepresentation()

        if self.distance_widget.GetEnabled():
            self.distance_widget.Off()  
            if hasattr(self, 'distance_text_actor'):
                self.distance_text_actor.SetInput("")  
            self.widget.GetRenderWindow().Render()  
        else:
            self.distance_widget.On()  

            # Function to update the text at every interation with one screen
            def update_distance(orientation):
                distance_in_pixels = self.distance_widget.GetRepresentation().GetDistance()

                # Get the spacing in mm
                spacing = self.image_data.GetSpacing()
                spacing_x, spacing_y, spacing_z = spacing

                # Get the distance according to the axis
                if orientation == 'axial':
                    distance_in_mm = distance_in_pixels * spacing_z  # Z
                elif orientation == 'sagittal':
                    distance_in_mm = distance_in_pixels * spacing_x  # X (plan sagittal)
                elif orientation == 'coronal':
                    distance_in_mm = distance_in_pixels * spacing_y  # Y (plan coronal)
                else:
                    distance_in_mm = distance_in_pixels * spacing_x 

                # Create a new text if necessary
                if not hasattr(self, 'distance_text_actor'):
                    self.distance_text_actor = vtk.vtkTextActor()
                    self.distance_text_actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
                    self.distance_text_actor.GetPositionCoordinate().SetValue(0.05, 0.95)
                    self.distance_text_actor.GetTextProperty().SetFontSize(15)
                    self.distance_text_actor.GetTextProperty().SetColor(1.0, 1.0, 1.0)
                    self.renderer.AddActor(self.distance_text_actor)

                self.distance_text_actor.SetInput(f"Distance: {distance_in_mm:.2f} mm")
                
                self.widget.GetRenderWindow().Render()
            self.distance_widget.AddObserver("InteractionEvent", lambda obj, event: update_distance(self.orientation))
            self.widget.GetRenderWindow().Render()


    ### Measuring Angle in Degrees

    def toggle_angle_measurement(self):
        if not hasattr(self, 'angle_widget'):
            self.angle_widget = vtk.vtkAngleWidget()
            self.angle_widget.SetInteractor(self.widget.GetRenderWindow().GetInteractor())
            self.angle_widget.CreateDefaultRepresentation()

        if self.angle_widget.GetEnabled():
            self.angle_widget.Off()
            if hasattr(self, 'angle_text_actor'): 
                self.angle_text_actor.SetInput("")  
            self.widget.GetRenderWindow().Render()
        else:
            self.angle_widget.On()

            # Function to update the angle text at every interaction
            def update_angle():
                angle_in_degrees = self.angle_widget.GetRepresentation().GetAngle()

                # Create a new text actor if necessary
                if not hasattr(self, 'angle_text_actor'): 
                    self.angle_text_actor = vtk.vtkTextActor()
                    self.angle_text_actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
                    self.angle_text_actor.GetPositionCoordinate().SetValue(0.50, 0.95)
                    self.angle_text_actor.GetTextProperty().SetFontSize(15)
                    self.angle_text_actor.GetTextProperty().SetColor(1.0, 1.0, 1.0)
                    self.renderer.AddActor(self.angle_text_actor)

                # Update the text actor with the angle
                self.angle_text_actor.SetInput(f"Angle: {angle_in_degrees:.2f}°")  # Renommer correctement

                self.widget.GetRenderWindow().Render()

            # Add an observer to update the angle whenever there is an interaction
            self.angle_widget.AddObserver("InteractionEvent", lambda obj, event: update_angle())
            self.widget.GetRenderWindow().Render()





# MAIN CLASS APP
#this is mainly divided in 2 parts: (1) the MPR visualization of the image slices and (2) the 3d view corner with the bones and prosthesis

class HipReplacementApp(QMainWindow):
    def __init__(self, image_path, mask_path, prosthesis_path, side):
        super().__init__()
        self.image_path = image_path  # CT image
        self.mask_path = mask_path  # segmentation mask
        self.prosthesis_path = prosthesis_path  # prosthesis model
        self.side = side

        self.setWindowTitle("Orthopedic Surgery Visualization")
        self.setGeometry(150, 150, 2000, 1600)

        self.central_widget = QWidget(self) #central widget: main container for all other UI elements
        self.setCentralWidget(self.central_widget)

        # Frame and layout
        self.frame = QFrame(self.central_widget) #container for all the rendered views
        self.layout = QGridLayout(self.frame) #to position widgets in a grid structure
        self.frame.setLayout(self.layout)

        self.mpr_views = {} #dictionary to store the multi-planar reconstruction views

        # Varaible for measures
            #2d slices
        self.distance_measure_mode_active = False 
        self.angle_measure_mode_active = False
        self.distance_button = None
        self.angle_button = None
            #buttons
        self.create_general_controls()

        self.create_slice_view()


    def create_slice_view(self): 
        nifti_reader = vtk.vtkNIFTIImageReader()
        nifti_reader.SetFileName(self.image_path)
        nifti_reader.Update()

        self.image_data = nifti_reader.GetOutput()

        for i, (plane, row, col) in enumerate(
            [("axial", 0, 0), ("coronal", 0, 1), ("sagittal", 1, 0)]
        ):
            mpr_visualizer = MPRVisualizer(self.image_data, plane, self.frame)  # Create MPRVisualizer instance 
            slider = mpr_visualizer.create_slider()  # Get the slider to update the slices correspondingly
            self.layout.addWidget(mpr_visualizer.widget, row * 2, col)  
            self.layout.addWidget(slider, row * 2 + 1, col) 
            self.mpr_views[plane] = mpr_visualizer

        self.init_3d_view()

    
 
    def normalize_units(self, mask_data, prosthesis_data): # this function normalizes the prosthesis in the same coordinate system as the mask
            image_bounds = mask_data.GetBounds()
            prosthesis_bounds = prosthesis_data.GetBounds()

            roi_size = [
                max(0, image_bounds[i * 2 + 1] - image_bounds[i * 2])
                for i in range(3)
            ]
            prosthesis_size = [
                (prosthesis_bounds[i * 2 + 1] - prosthesis_bounds[i * 2])*10
                for i in range(3)
            ]
            print(roi_size,prosthesis_size)
            scale_factor = max(roi_size[i] / prosthesis_size[i] for i in range(3))
            return scale_factor


    def prosthesis_rendering(self):
        # PROSTHESIS MODEL RENDERING (surface)
        # Prosthesis visualization as a surface
        self.prosthesis_reader = vtk.vtkSTLReader()
        self.prosthesis_reader.SetFileName(self.prosthesis_path)
        self.prosthesis_reader.Update()

        # Normalize Units
        scale_factor = self.normalize_units(self.mask_reader.GetOutput(), self.prosthesis_reader.GetOutput())

        # mapper: since our input data is already an stl file, we dont need the merching cubes
        self.prosthesis_mapper = vtk.vtkPolyDataMapper()
        self.prosthesis_mapper.SetInputConnection(self.prosthesis_reader.GetOutputPort())

        self.prosthesis_actor = vtk.vtkActor()
        self.prosthesis_actor.SetMapper(self.prosthesis_mapper)
        self.prosthesis_actor.SetScale(scale_factor, scale_factor, scale_factor)
        self.prosthesis_actor.GetProperty().SetColor(1.0, 0.5, 0.0)  # Orange
        self.prosthesis_actor.GetProperty().SetOpacity(1.0)  # Fully opaque

        # Prosthesis Transformation Based on Side
        self.prosthesis_transform = vtk.vtkTransform()

        if self.side == "Right":
            print('Right chosen')
            # Translation adjustment
            self.prosthesis_transform.Translate(58, 145, 68)  # Fine-tuned translation closer to the joint

            # Rotation adjustments
            self.prosthesis_transform.RotateWXYZ(90, 0, 1, 0)   # Flip around the Y-axis (kept as-is)
            self.prosthesis_transform.RotateWXYZ(85, 1, 0, 0)   # Refined rotation along X-axis for ball position
            self.prosthesis_transform.RotateWXYZ(-45, 0, 0, 1)  # Adjust Z-axis rotation for shaft alignment
            self.prosthesis_transform.RotateWXYZ(20, -1, -0.2, 0)  # Minor tilt correction
            self.prosthesis_transform.RotateWXYZ(15, 0, 0, 1)   # Small Z-axis fine-tuning
            

        elif self.side == "Left":
            print("Left chosen")
            self.prosthesis_transform.Translate(280, 165, 30)
            self.prosthesis_transform.RotateWXYZ(-90, 1, 0, 0)
            self.prosthesis_transform.RotateWXYZ(45, 0, 1, 1)
            self.prosthesis_transform.RotateWXYZ(-30, 0, 1, 0)
        
        # Apply the transformation
        self.prosthesis_actor.SetUserTransform(self.prosthesis_transform)



    def mask_rendering(self):
        # BONES MASK RENDERING
        # Volume Rendering for Segmentation (Mask)
        self.mask_reader = vtk.vtkNIFTIImageReader()
        self.mask_reader.SetFileName(self.mask_path)
        self.mask_reader.Update()

        # Volume mapper for the hip bones segmentation mask
        self.volume_mapper = vtk.vtkGPUVolumeRayCastMapper()
        self.volume_mapper.SetInputConnection(self.mask_reader.GetOutputPort())

        # Volume properties (color transfer functions)
        volume_color = vtk.vtkColorTransferFunction()
        volume_color.AddRGBPoint(0, 0.,0., 0.)  # Background is black
        volume_color.AddRGBPoint(0.5, 0.9,0.9, 0.9)  # Inside color 
        volume_color.AddRGBPoint(1, 0.9,0.9, 0.9)  # Bone color (light beige)

        # Volume properties (opacity)
        volume_opacity = vtk.vtkPiecewiseFunction()
        volume_opacity.AddPoint(0, 0.0)  # Background is fully transparent
        volume_opacity.AddPoint(1, 1)  

        volume_property = vtk.vtkVolumeProperty()
        volume_property.SetColor(volume_color)
        volume_property.SetScalarOpacity(volume_opacity)
        volume_property.ShadeOn()
        volume_property.SetInterpolationTypeToLinear()
        volume_property.SetAmbient(0.3)  # Adjust ambient lighting
        volume_property.SetDiffuse(0.7)  # Adjust diffuse lighting
        volume_property.SetSpecular(0.5)  # Add specular highlights

        # defien the actor and connect it to the mapper
        self.volume = vtk.vtkVolume() #actor
        self.volume.SetMapper(self.volume_mapper)
        self.volume.SetProperty(volume_property)


    """Now, all the buttons"""

    def opacity_toggle_button(self, widget, volume_property): # button to change the opacity of the mask
        # Add a button for toggling opacity
        self.toggle_button_opacity = QPushButton("Toggle Opacity")
        self.toggle_button_opacity.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Track the current opacity state
        self.is_semitransparent = True  # Default: semi-transparent

        def toggle_opacity():
            if self.is_semitransparent:
                volume_property.GetScalarOpacity().AddPoint(1, 1.0)  # Bone is fully opaque
                self.toggle_button_opacity.setText("Semi-Transparent")
            else:
                volume_property.GetScalarOpacity().AddPoint(1, 0.2)  # Bone is semi-transparent
                self.toggle_button_opacity.setText("Fully Opaque")
            
            # Update flag and render
            self.is_semitransparent = not self.is_semitransparent
            widget.GetRenderWindow().Render()

        # Connect the button to the toggle_opacity function
        self.toggle_button_opacity.clicked.connect(toggle_opacity)


    def scaling_prosthesis_button(self, widget): # button to scale up or down the prosthesis

        self.scale_up_button = QPushButton("Scale Up", self.frame)
        self.scale_down_button = QPushButton("Scale Down", self.frame)

        self.scale_up_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.scale_down_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        def scaling_prosthesis(scale_factor):

            current_scale = self.prosthesis_actor.GetScale()
            new_scale = (
                current_scale[0] * scale_factor,
                current_scale[1] * scale_factor,
                current_scale[2] * scale_factor
            )
            self.prosthesis_actor.SetScale(new_scale)
            widget.GetRenderWindow().Render() 

        self.scale_up_button.clicked.connect(lambda: scaling_prosthesis(1.1))  # Scale up by 10%
        self.scale_down_button.clicked.connect(lambda: scaling_prosthesis(0.9)) 


    def plane_widget_setup (self, widget): #plane widget
        # Cutting plane
        self.plane_widget = vtk.vtkImplicitPlaneWidget()
        self.plane_widget.SetInteractor(widget.GetRenderWindow().GetInteractor())
        self.plane_widget.SetPlaceFactor(1.25)  # Adjust plane size
        self.plane_widget.SetInputData(self.mask_reader.GetOutput())  # Attach to the volume reader
        self.plane_widget.PlaceWidget()
        self.plane_widget.Off()  # Initially hide the plane widget

        # Ensure the plane widget interactions are enabled
        interactor = widget.GetRenderWindow().GetInteractor()
        interactor.Initialize()

        interactor_style = vtk.vtkInteractorStyleTrackballCamera()  # Controlled rotation
        interactor.SetInteractorStyle(interactor_style)

        # Create vtkPlane for volume and prosthesis clipping
        self.cutting_plane = vtk.vtkPlane()
        self.plane_widget.GetPlane(self.cutting_plane)  # Get initial plane position



    def toggle_button_setup(self, widget): # button that makes appear the plane widget
        self.toggle_button = QPushButton("Plane Widget", self.frame)
        self.toggle_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        def toggle_plane_widget():
            if self.plane_widget.GetEnabled():
                self.plane_widget.Off()
            else:
                self.plane_widget.On()
            widget.GetRenderWindow().Render()

        self.toggle_button.clicked.connect(toggle_plane_widget)


    def cut_button_setup(self, widget): # button that makes a cut using the plane widget
        self.cut_button = QPushButton("Apply Cut", self.frame)
        self.cut_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        def apply_cut():
            # Update the cutting plane parameters
            self.plane_widget.GetPlane(self.cutting_plane)

            # Clipping for the bone segmentation mask (volume)
            self.volume_mapper.RemoveAllClippingPlanes()
            self.volume_mapper.AddClippingPlane(self.cutting_plane)

            self.prosthesis_mapper.RemoveAllClippingPlanes()
            self.prosthesis_mapper.AddClippingPlane(self.cutting_plane)

            # Re-render
            widget.GetRenderWindow().Render()

        self.cut_button.clicked.connect(apply_cut)


    def undo_button_setup(self, widget): # button to undo the cut
        self.undo_button = QPushButton("Undo Cut", self.frame)
        self.undo_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        def undo_cut():
            # Reset volume clipping
            self.volume_mapper.RemoveAllClippingPlanes()
            self.prosthesis_mapper.RemoveAllClippingPlanes()

            # Re-render
            widget.GetRenderWindow().Render()

        self.undo_button.clicked.connect(undo_cut)
    
    

    def mpr_slice_updates(self): # function that can change image slices in the mpr view depending on plane widget
        def update_slices(widget, event):
            slicing_origin = [0.0, 0.0, 0.0]
            self.plane_widget.GetOrigin(slicing_origin)

            for plane, visualizer in self.mpr_views.items():
                slicing_axis = {"axial": 2, "coronal": 1, "sagittal": 0}[plane]
                origin = list(visualizer.reslice.GetResliceAxesOrigin())
                origin[slicing_axis] = slicing_origin[slicing_axis]
                visualizer.reslice.SetResliceAxesOrigin(*origin)
                visualizer.reslice.Update()
                visualizer.renderer.GetRenderWindow().Render()

        self.plane_widget.AddObserver("InteractionEvent", update_slices)
        

    def prosthesis_buttons(self, widget): # these buttons can move and rotate the prosthesis
        translation_step = 5  # Step size for translation
        rotation_step = 5     # Step size for rotation in degrees

        # Helper functions for translation and rotation
        def translate(axis, step):
            #self.prosthesis_transform.Identity()
            if axis == 'x': 
                self.prosthesis_transform.Translate(step, 0, 0)
            elif axis == 'y':
                self.prosthesis_transform.Translate(0, step, 0)
            elif axis == 'z': 
                self.prosthesis_transform.Translate(0, 0, step)
            widget.GetRenderWindow().Render()

        def rotate(axis, step):
            #self.prosthesis_transform.Identity()
            if axis == 'x':
                self.prosthesis_transform.RotateWXYZ(step, 1, 0, 0)
            elif axis == 'y':
                self.prosthesis_transform.RotateWXYZ(step, 0, 1, 0)
            elif axis == 'z':
                self.prosthesis_transform.RotateWXYZ(step, 0, 0, 1)
            widget.GetRenderWindow().Render()

        # Translation Buttons
        translation_buttons = [
            ("Translate +X", lambda: translate('x', translation_step)),
            ("Translate -X", lambda: translate('x', -translation_step)),
            ("Translate +Y", lambda: translate('y', translation_step)),
            ("Translate -Y", lambda: translate('y', -translation_step)),
            ("Translate +Z", lambda: translate('z', translation_step)),
            ("Translate -Z", lambda: translate('z', -translation_step)),
        ]

        # Rotation Buttons
        rotation_buttons = [
            ("Rotate +X", lambda: rotate('x', rotation_step)),
            ("Rotate -X", lambda: rotate('x', -rotation_step)),
            ("Rotate +Y", lambda: rotate('y', rotation_step)),
            ("Rotate -Y", lambda: rotate('y', -rotation_step)),
            ("Rotate +Z", lambda: rotate('z', rotation_step)),
            ("Rotate -Z", lambda: rotate('z', -rotation_step)),
        ]

        return translation_buttons, rotation_buttons
      

    def create_general_controls(self):
        # Button for distance measurement
        self.distance_button = QPushButton("Distance Measurement Mode", self.frame)
        self.distance_button.clicked.connect(self.toggle_distance_measurement_mode)  # Connect to distance measurement mode

        # Button for angle measurement
        self.angle_button = QPushButton("Angle Measurement Mode", self.frame)
        self.angle_button.clicked.connect(self.toggle_angle_measurement_mode)  # Connect to angle measurement mode


    def add_buttons_to_layout(self, widget, translation_buttons, rotation_buttons):  # function to place all the buttons

        # create the animation view buttons
        self.front_view_button = QPushButton("Front View")
        self.front_view_button.clicked.connect(lambda: self.animate_camera_to_view(
            position=[self.mask_center[0], self.mask_center[1] - 300, self.mask_center[2]],  # Front position
            focal_point=self.mask_center,
            view_up=[0, 0, 1]  # Align Z-axis up
        ))

        self.side_view_button = QPushButton("Side View")
        self.side_view_button.clicked.connect(lambda: self.animate_camera_to_view(
            position=[self.mask_center[0] + 300, self.mask_center[1], self.mask_center[2]],  # Side position
            focal_point=self.mask_center,
            view_up=[0, 0, 1]  # Align Z-axis up
        ))

        self.top_view_button = QPushButton("Top View")
        self.top_view_button.clicked.connect(lambda: self.animate_camera_to_view(
            position=[self.mask_center[0], self.mask_center[1], self.mask_center[2] + 300],  # Top position
            focal_point=self.mask_center,
            view_up=[0, 1, 0]  # Align Y-axis up
        ))


        # Add the main widget (render window) to the layout
        self.layout.addWidget(widget, 2, 1)

        # Create a vertical layout for all button sections
        button_column_layout = QVBoxLayout()
        button_column_layout2 = QVBoxLayout()
        button_column_layout3 = QVBoxLayout()

        # Section: Measurement Mode
        measurement_group = QGroupBox("Measurement Mode")
        measurement_layout = QVBoxLayout()
        measurement_layout.addWidget(self.angle_button)
        measurement_layout.addWidget(self.distance_button)
        measurement_group.setLayout(measurement_layout)
        button_column_layout.addWidget(measurement_group)

        # Section: 3D Rendering Controls
        rendering_group = QGroupBox("3D Rendering")
        rendering_layout = QVBoxLayout()
        rendering_layout.addWidget(self.toggle_button_opacity)
        rendering_layout.addWidget(self.scale_up_button)
        rendering_layout.addWidget(self.scale_down_button)
        rendering_group.setLayout(rendering_layout)
        button_column_layout.addWidget(rendering_group)

        # Section: Plane Widget Controls
        plane_widget_group = QGroupBox("Plane Widget Controls")
        plane_widget_layout = QVBoxLayout()
        plane_widget_layout.addWidget(self.toggle_button)
        plane_widget_layout.addWidget(self.cut_button)
        plane_widget_layout.addWidget(self.undo_button)
        plane_widget_group.setLayout(plane_widget_layout)
        button_column_layout.addWidget(plane_widget_group)

        # Section: View Controls
        view_group = QGroupBox("Animation view Controls")
        view_layout = QVBoxLayout()
        view_layout.addWidget(self.front_view_button)
        view_layout.addWidget(self.side_view_button)
        view_layout.addWidget(self.top_view_button)
        view_group.setLayout(view_layout)
        button_column_layout.addWidget(view_group)

        # Add the column layout to the main layout
        self.layout.addLayout(button_column_layout, 0, 6, 6, 1)


        trans_group = QGroupBox("Prosthesis translation")
        trans_layout = QVBoxLayout()

        rot_group = QGroupBox("Prosthesis rotation")
        rot_layout = QVBoxLayout()

        # Add translation buttons to the prosthesis button layout
        for i, (label, func) in enumerate(translation_buttons):
            button = QPushButton(label, self.frame) 
            button.clicked.connect(func)
            trans_layout.addWidget(button)
        trans_group.setLayout(trans_layout)
        button_column_layout2.addWidget(trans_group)

        # Add rotation buttons to the prosthesis button layout
        for i, (label, func) in enumerate(rotation_buttons):
            button = QPushButton(label, self.frame)
            button.clicked.connect(func)
            rot_layout.addWidget(button)
        rot_group.setLayout(rot_layout)
        button_column_layout3.addWidget(rot_group)

        self.layout.addLayout(button_column_layout2, 0, 7, 6, 1)
        self.layout.addLayout(button_column_layout3, 0, 8, 6, 1)


    def animate_camera_to_view(self, position, focal_point, view_up, duration=1500, zoom_factor=0.5): # animation function to change the viewpoint of the camara
        camera = self.renderer.GetActiveCamera()

        start_position = camera.GetPosition()
        start_focal_point = camera.GetFocalPoint()
        start_view_up = camera.GetViewUp()

        # Calculate the initial distance between the camera and the focal point
        initial_distance = vtk.vtkMath.Distance2BetweenPoints(start_position, start_focal_point) ** 0.5

        # Calculate the new camera position with the desired zoom factor
        direction_vector = [
            (focal_point[i] - position[i]) for i in range(3)
        ]
        distance_adjustment = initial_distance / zoom_factor
        adjusted_position = [
            focal_point[i] - direction_vector[i] * distance_adjustment / initial_distance
            for i in range(3)
        ]

        steps = 100  # Number of animation steps
        interval = duration // steps

        def interpolate(t, start, end):
            return start + t * (end - start)

        def update_camera(step):
            t = step / steps

            # Interpolate position, focal point, and view up
            new_position = [interpolate(t, start_position[i], adjusted_position[i]) for i in range(3)]
            new_focal_point = [interpolate(t, start_focal_point[i], focal_point[i]) for i in range(3)]
            new_view_up = [interpolate(t, start_view_up[i], view_up[i]) for i in range(3)]

            camera.SetPosition(*new_position)
            camera.SetFocalPoint(*new_focal_point)
            camera.SetViewUp(*new_view_up)

            self.renderer.ResetCameraClippingRange()
            self.renderer.GetRenderWindow().Render()

            if step < steps:
                QTimer.singleShot(interval, lambda: update_camera(step + 1))

        # Start the animation
        update_camera(0)


    
    ## Distance
    def toggle_distance_measurement_mode(self):
        self.distance_measure_mode_active = not self.distance_measure_mode_active 

        # For 2d slices measures
        for _, visualizer in self.mpr_views.items():
            if self.distance_measure_mode_active:
                visualizer.toggle_distance_measurement()
                self.distance_button.setStyleSheet("background-color: green; color: white;") 
                self.distance_button.setText("Distance Mode: ON")
            else:
                if visualizer.distance_widget and visualizer.distance_widget.GetEnabled():
                    visualizer.distance_widget.Off()
                    if hasattr(visualizer, 'distance_text_actor'):
                        visualizer.widget.GetRenderWindow().Render() 
                self.distance_button.setStyleSheet("")  
                self.distance_button.setText("Distance Measurement Mode")

    ## Angles
                            
    def toggle_angle_measurement_mode(self):
        self.angle_measure_mode_active = not self.angle_measure_mode_active
        for _, visualizer in self.mpr_views.items():
            if self.angle_measure_mode_active:
                visualizer.toggle_angle_measurement()  # Activate the angle widget
                self.angle_button.setStyleSheet("background-color: blue; color: white;")  # Active state
                self.angle_button.setText("Angle Mode: ON")
            else:
                if visualizer.angle_widget and visualizer.angle_widget.GetEnabled():
                    visualizer.angle_widget.Off()  # Correctly deactivate the angle widget
                    if hasattr(visualizer, 'angle_text_actor'):
                        visualizer.widget.GetRenderWindow().Render()
                self.angle_button.setStyleSheet("")  # Default style (inactive)
                self.angle_button.setText("Angle Measurement Mode")

    
    
    
    def init_3d_view(self):
        # widget
        widget = QVTKRenderWindowInteractor(self.frame)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # renderer
        self.renderer = vtk.vtkRenderer()
        widget.GetRenderWindow().AddRenderer(self.renderer)

        # MASK RENDERING
        self.mask_rendering()

        # Calculate mask center
        mask_bounds = self.volume.GetBounds()
        self.mask_center = [
            (mask_bounds[0] + mask_bounds[1]) / 2,
            (mask_bounds[2] + mask_bounds[3]) / 2,
            (mask_bounds[4] + mask_bounds[5]) / 2,
        ]

        # PROSTHESIS MODEL RENDERING (surface)
        self.prosthesis_rendering()

        # Add a reference axis to the scene
        axes = vtk.vtkAxesActor()
        axes.SetTotalLength(70, 70, 70)
        axes.GetXAxisCaptionActor2D().GetTextActor().SetTextScaleModeToNone()
        axes.GetYAxisCaptionActor2D().GetTextActor().SetTextScaleModeToNone()
        axes.GetZAxisCaptionActor2D().GetTextActor().SetTextScaleModeToNone()
        axes.SetPosition(-20, -20, -20)

        # Add volume, surface, and axes rendering to the renderer
        self.renderer.AddVolume(self.volume)
        self.renderer.AddActor(self.prosthesis_actor)
        self.renderer.AddActor(axes)
        self.renderer.SetBackground(0.1, 0.1, 0.1)
        self.renderer.GetRenderWindow().Render()

        # Setup additional features
        self.plane_widget_setup(widget)
        self.toggle_button_setup(widget)
        self.cut_button_setup(widget)
        self.undo_button_setup(widget)

        self.mpr_slice_updates()

        # Setup Prosthesis Manipulation Buttons
        translation_buttons, rotation_buttons = self.prosthesis_buttons(widget)
        self.opacity_toggle_button(widget, self.volume.GetProperty())
        self.scaling_prosthesis_button(widget)

        # Add widgets to the layout
        self.add_buttons_to_layout(widget, translation_buttons, rotation_buttons)


    def closeEvent(self, event):
        # Proper cleanup for all MPR views
        for plane, visualizer in self.mpr_views.items():  # Access MPRVisualizer directly
            widget = visualizer.widget  # Access widget from visualizer
            render_window = widget.GetRenderWindow()
            interactor = render_window.GetInteractor()

            # Finalize and disable interactor
            if interactor:
                interactor.Disable()
                interactor.TerminateApp()

            # Finalize render window
            render_window.Finalize()

            # Mark widget for deletion
            widget.deleteLater()

        # Cleanup the 3D view as well
        for i in range(self.layout.count()):
            item = self.layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, QVTKRenderWindowInteractor):
                render_window = widget.GetRenderWindow()
                interactor = render_window.GetInteractor()

                if interactor:
                    interactor.Disable()
                    interactor.TerminateApp()

                render_window.Finalize()
                widget.deleteLater()

        # Ensure the main frame is cleaned up
        self.frame.deleteLater()

        # Proceed with the default close event
        event.accept()


    def visualize(self):
        self.show()




if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Call the function to get image, mask, prosthesis files, and side
    image_path, mask_path, prosthesis_path, side = choose_files()

    # Ensure all input files exist
    if not os.path.exists(image_path) or not os.path.exists(mask_path) or not os.path.exists(prosthesis_path):
        print("Error: Ensure all input files are present and valid.")
        sys.exit(1)

    # Initialize the application with the chosen parameters
    main_window = HipReplacementApp(image_path, mask_path, prosthesis_path, side)
    main_window.visualize()
    sys.exit(app.exec_())



