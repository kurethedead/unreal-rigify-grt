import bpy
from bpy.utils import register_class, unregister_class
import re

# info about add on
bl_info = {
    "name": "Unreal Rigify To GRT",
    "version": (1, 0, 0),
    "author": "kurethedead",
    "location": "3DView",
    "description": "Automating GRT rig generation from a Rigify metarig for use with Unreal",
    "category": "Armature",
    "blender": (4, 1, 0),
}


class GenerateRig(bpy.types.Operator):
    # set bl_ properties
    bl_description = 'Generates a GRT rig from the selected Rigify metarig. An optional add-on rig will be joined to the Rigify control rig before generating the GRT deform rig. The selected bones in this add-on rig are parented to the "head" bone.'
    bl_idname = "object.generate_grt_rig_from_rigify_metarig"
    bl_label = "Rigify Metarig To GRT"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        if len(context.selected_objects) == 0:
            raise RuntimeError("Armature not selected.")
        elif type(context.selected_objects[0].data) is not bpy.types.Armature:
            raise RuntimeError("Armature not selected.")

        metarigObj = context.selected_objects[0]

        if context.mode != "POSE":
            bpy.ops.object.mode_set(mode="POSE")

        # Keep track of these bones to reparent in GRT rig
        faceBoneNames = [
            bone.name for bone in metarigObj.data.bones["spine.006"].children_recursive
        ]

        # Make IK rig use single bones for each limb, allowing for 2-bone game IK to work
        for limbName in ["upper_arm.L", "upper_arm.R", "thigh.L", "thigh.R"]:
            poseBone = metarigObj.pose.bones[limbName]
            poseBone.rigify_parameters.segments = 1

        for limbName in ["thigh.L", "thigh.R"]:
            # Set rotation axis so that knees bend forward
            poseBone = metarigObj.pose.bones[limbName]
            poseBone.rigify_parameters.rotation_axis = "x"
            poseBone.rigify_parameters.auto_align_extremity = True

        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.pose.rigify_generate()
        ikRigObj = bpy.context.active_object

        ikRigObj.show_in_front = True

        # Set IK parent for hand/feet/torso to 0, making them move independent of the root bone
        # This lets us constrain the root bone to the torso, so we get free root motion
        for limbName in [
            "upper_arm_parent.L",
            "upper_arm_parent.R",
            "thigh_parent.L",
            "thigh_parent.R",
        ]:
            poseBone = ikRigObj.pose.bones[limbName]
            poseBone["IK_parent"] = 0

        ikRigObj.pose.bones["torso"]["torso_parent"] = 0

        ikRigObj.data.bones["root"].use_deform = True
        rootPoseBone = ikRigObj.pose.bones["root"]
        constraint = rootPoseBone.constraints.new(type="COPY_LOCATION")
        constraint.target = ikRigObj
        constraint.subtarget = "torso"
        constraint.use_x = False
        constraint.use_y = True
        constraint.use_z = False

        # Add shape key rig if applicable.
        shapeKeyRig = bpy.context.scene.rigifyToGRTProperty.shapeKeyRig
        shapeKeyRigBoneNames = []
        if shapeKeyRig:
            shapeKeyRigBoneNames = [
                bone.name for bone in shapeKeyRig.data.bones if bone.parent is None
            ]
            bpy.ops.object.select_all(action="DESELECT")
            shapeKeyRig.select_set(True)
            ikRigObj.select_set(True)
            bpy.context.view_layer.objects.active = ikRigObj
            bpy.ops.object.join()

            bpy.ops.object.mode_set(mode="EDIT")
            controlEditBones = ikRigObj.data.edit_bones
            for childBoneName in shapeKeyRigBoneNames:
                controlEditBones[childBoneName].parent = controlEditBones["head"]

            # TODO: Handle bone parenting, not all bones should be parented?

        # Set ik rig to source armature - need it for game rig generation, so we just set other settings while we're here
        bpy.ops.object.mode_set(mode="OBJECT")
        GRTSettings = context.scene.GRT_Action_Bakery_Global_Settings
        GRTSettings.Overwrite = True
        GRTSettings.Push_to_NLA = False
        GRTSettings.Source_Armature = ikRigObj
        
        bpy.ops.gamerigtool.generate_game_rig(Deform_Armature_Name="Armature")
        bpy.ops.object.mode_set(mode="EDIT")

        # Reparent bones on GRT rig so that hierarchy makes sense in Unreal
        # Every bone should be in same hierarchy under the root bone
        GRTRigObj = bpy.context.active_object
        GRTSettings.Target_Armature = GRTRigObj
        editBones = GRTRigObj.data.edit_bones

        # Arms to Shoulders
        editBones["DEF-upper_arm.L"].parent = editBones["DEF-shoulder.L"]
        editBones["DEF-upper_arm.R"].parent = editBones["DEF-shoulder.R"]

        # Shoulders/Breasts to Spine
        for childBoneName in [
            "DEF-breast.R",
            "DEF-breast.L",
            "DEF-shoulder.R",
            "DEF-shoulder.L",
        ]:
            editBones[childBoneName].parent = editBones["DEF-spine.003"]

        # Thighs to Pelvis to Spine
        editBones["DEF-thigh.L"].parent = editBones["DEF-pelvis.L"]
        editBones["DEF-thigh.R"].parent = editBones["DEF-pelvis.R"]
        editBones["DEF-pelvis.L"].parent = editBones["DEF-spine"]
        editBones["DEF-pelvis.R"].parent = editBones["DEF-spine"]

        # Face to Head
        for childName in faceBoneNames:
            name = f"DEF-{childName}"
            if name in editBones:
                editBones[name].parent = editBones["DEF-spine.006"]

        # Shape Key Bones to Head
        for childName in shapeKeyRigBoneNames:
            editBones[childName].parent = editBones["DEF-spine.006"]

        bpy.ops.object.mode_set(mode="OBJECT")      

        # Add/Reorder collections
        collections = {}
        sceneCollection = bpy.context.scene.collection
        activeCollection = bpy.context.view_layer.active_layer_collection.collection
        layerNames = ["Deform", "Control", "Metarig"]
        for name in layerNames:
            if name not in bpy.data.collections:
                collections[name] = bpy.data.collections.new(name)
                sceneCollection.children.link(collections[name])
            else:
                collections[name] = bpy.data.collections[name]

        # children = sceneCollection.children[:]
        # try:
        #    for i in range(len(layerNames)):
        #        childCollection = sceneCollection.children[layerNames[i]]
        #        children.remove(childCollection)
        #        children.insert(i + 1, childCollection)
        #        if layerNames[i] != "Control":
        #            childCollection.hide_viewport = True
        #
        #    for child in children:
        #        sceneCollection.children.unlink(child)
        #        sceneCollection.children.link(child)
        # except ValueError:
        #    print("Control/Deform collection not found.")

        # Add rigs to correct collections
        for name, rig in tuple(zip(layerNames, [GRTRigObj, ikRigObj, metarigObj])):
            if not rig:
                continue
            if rig not in collections[name].objects[:]:
                collections[name].objects.link(rig)
                if rig in activeCollection.objects[:]:
                    activeCollection.objects.unlink(rig)

        metarigObj.hide_set(True)

        self.report({"INFO"}, "Finished")
        return {"FINISHED"}  # must return a set


class TransferShapeKeyDrivers(bpy.types.Operator):
    # set bl_ properties
    bl_description = "Copies shape key driver settings from the active object to all selected objects for any shared shape key names. This optionally sets a new target object for all driver variables."
    bl_idname = "object.transfer_shape_key_drivers"
    bl_label = "Transfer Shape Key Drivers By Name"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        if len(context.selected_objects) < 2:
            self.report({"ERROR"}, "Not enough objects selected.")
            return {"FINISHED"}
        elif bpy.context.view_layer.objects.active is None:
            self.report({"ERROR"}, "No active object selected.")
            return {"FINISHED"}

        for obj in context.selected_objects:
            if not isinstance(obj.data, bpy.types.Mesh):
                raise RuntimeError("A selected object is not a mesh.")

        source = bpy.context.view_layer.objects.active
        targets = [obj for obj in context.selected_objects if obj is not source]

        targetRig = bpy.context.scene.rigifyToGRTProperty.rigObj

        for target in targets:
            if source.data.shape_keys.animation_data is None:
                self.report({"ERROR"}, "No shape key data found on source object.")
                return {"FINISHED"}
            for fcurve in source.data.shape_keys.animation_data.drivers:
                sourceDriver = fcurve.driver
                shapeKeyName = self.getShapeKeyNameFromDriver(fcurve)
                targetShapeKeys = target.data.shape_keys
                if shapeKeyName and shapeKeyName in targetShapeKeys.key_blocks:
                    targetShapeKey = targetShapeKeys.key_blocks[shapeKeyName]
                    targetDriver = targetShapeKey.driver_add("value").driver
                    targetDriver.type = sourceDriver.type
                    targetDriver.expression = sourceDriver.expression

                    for driverVar in sourceDriver.variables:
                        targetDriverVar = targetDriver.variables.new()
                        targetDriverVar.name = driverVar.name
                        targetDriverVar.type = driverVar.type

                        for i in range(len(driverVar.targets)):
                            for value in [
                                "bone_target",
                                "data_path",
                                "id",
                                "rotation_mode",
                                "transform_space",
                                "transform_type",
                            ]:
                                setattr(
                                    targetDriverVar.targets[i],
                                    value,
                                    getattr(driverVar.targets[i], value),
                                )

                            # New shape key drivers should target our deform rig
                            if targetRig:
                                targetDriverVar.targets[i].id = targetRig

                    # Need to do this to force update of driver
                    targetDriver.expression = targetDriver.expression

                driver = fcurve.driver
                driver.expression

        self.report({"INFO"}, "Finished")
        return {"FINISHED"}  # must return a set

    def getShapeKeyNameFromDriver(self, fcurve):
        match = re.match(r"key\_blocks\[\"(.*)\"\]\.value", fcurve.data_path)
        if match:
            return match.group(1)
        else:
            return None


class ToolsPanel(bpy.types.Panel):
    bl_idname = "RIGIFY_GRT_PT_global_tools"
    bl_label = "Unreal Rigify To GRT"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Game Rig Tool"

    @classmethod
    def poll(cls, context):
        return True

    # called every frame
    def draw(self, context):
        col = self.layout.column()

        prop = bpy.context.scene.rigifyToGRTProperty
        generateRig = col.operator(GenerateRig.bl_idname)
        prop_split(col, prop, "shapeKeyRig", "Add-on Rig")
        col.label(text="Make sure all add-on bones are deformable.")

        transferShapeKeyDrivers = col.operator(TransferShapeKeyDrivers.bl_idname)
        prop_split(col, prop, "rigObj", "New Driver Target")


def prop_split(layout, data, field, name, **prop_kwargs):
    split = layout.split(factor=0.5)
    split.label(text=name)
    split.prop(data, field, text="", **prop_kwargs)


def pollShapeKeyRig(self, obj):
    return isinstance(obj.data, bpy.types.Armature)


class RigifyToGRTProperty(bpy.types.PropertyGroup):
    shapeKeyRig: bpy.props.PointerProperty(
        type=bpy.types.Object,
        poll=pollShapeKeyRig,
    )

    rigObj: bpy.props.PointerProperty(
        type=bpy.types.Object,
        poll=pollShapeKeyRig,
    )


classes = [GenerateRig, TransferShapeKeyDrivers, ToolsPanel, RigifyToGRTProperty]


def register():
    for cls in classes:
        register_class(cls)

    bpy.types.Scene.rigifyToGRTProperty = bpy.props.PointerProperty(
        type=RigifyToGRTProperty
    )


def unregister():
    del bpy.types.Scene.rigifyToGRTProperty

    for cls in classes:
        unregister_class(cls)
