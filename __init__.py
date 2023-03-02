import bpy
from bpy.utils import register_class, unregister_class

# info about add on
bl_info = {
    "name": "Rigify GRT Tools",
    "version": (1, 0, 0),
    "author": "kurethedead",
    "location": "3DView",
    "description": "Scripts for automating processing of using Rigify, GRT, and Unreal.",
    "category": "Import-Export",
    "blender": (3, 2, 0),
}


class SetLimbSegments(bpy.types.Operator):
    # set bl_ properties
    bl_description = (
        "(Rigify Metarig) Set Limb Segments to 1 for limbs, so that game IK works."
    )
    bl_idname = "object.set_limb_segments"
    bl_label = "Set Limb Segments"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        if len(context.selected_objects) == 0:
            raise RuntimeError("Armature not selected.")
        elif type(context.selected_objects[0].data) is not bpy.types.Armature:
            raise RuntimeError("Armature not selected.")

        armatureObj = context.selected_objects[0]

        if context.mode != "POSE":
            bpy.ops.object.mode_set(mode="POSE")

        for limbName in ["upper_arm.L", "upper_arm.R", "thigh.L", "thigh.R"]:
            poseBone = armatureObj.pose.bones[limbName]
            poseBone.rigify_parameters.segments = 1

        bpy.ops.object.mode_set(mode="OBJECT")

        self.report({"INFO"}, "Finished")
        return {"FINISHED"}  # must return a set


class SetIKParentsAndGenerateRig(bpy.types.Operator):
    # set bl_ properties
    bl_description = "(Rigify IK Rig) Sets IK parent for hand/foot/torso IK to 0, to move independently of root bone. Then generates rig and parents bones correctly."
    bl_idname = "object.set_ik_and_generate"
    bl_label = "Set IK Parents And Generate Rig"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        if len(context.selected_objects) == 0:
            raise RuntimeError("Armature not selected.")
        elif type(context.selected_objects[0].data) is not bpy.types.Armature:
            raise RuntimeError("Armature not selected.")

        armatureObj = context.selected_objects[0]

        if context.mode != "POSE":
            bpy.ops.object.mode_set(mode="POSE")

        for limbName in [
            "upper_arm_parent.L",
            "upper_arm_parent.R",
            "thigh_parent.L",
            "thigh_parent.R",
        ]:
            poseBone = armatureObj.pose.bones[limbName]
            poseBone["IK_parent"] = 0

        armatureObj.pose.bones["torso"]["torso_parent"] = 0

        armatureObj.data.bones["root"].use_deform = True
        rootPoseBone = armatureObj.pose.bones["root"]
        constraint = rootPoseBone.constraints.new(type="COPY_ROTATION")
        constraint.target = armatureObj
        constraint.subtarget = "hips"
        constraint.use_x = False
        constraint.use_z = False

        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.gamerigtool.generate_game_rig(Deform_Armature_Name="Armature")
        bpy.ops.object.mode_set(mode="EDIT")

        editBones = bpy.context.active_object.data.edit_bones
        print(editBones[:])
        editBones["DEF-upper_arm.L"].parent = editBones["DEF-shoulder.L"]
        editBones["DEF-upper_arm.R"].parent = editBones["DEF-shoulder.R"]

        for childBoneName in [
            "DEF-breast.R",
            "DEF-breast.L",
            "DEF-shoulder.R",
            "DEF-shoulder.L",
        ]:
            editBones[childBoneName].parent = editBones["DEF-spine.003"]

        editBones["DEF-thigh.L"].parent = editBones["DEF-pelvis.L"]
        editBones["DEF-thigh.R"].parent = editBones["DEF-pelvis.R"]
        editBones["DEF-pelvis.L"].parent = editBones["DEF-spine"]
        editBones["DEF-pelvis.R"].parent = editBones["DEF-spine"]

        children = [
            "nose",
            "lip.T.L",
            "lip.B.L",
            "jaw",
            "ear.L",
            "ear.R",
            "lip.T.R",
            "lip.B.R",
            "brow.B.L",
            "lid.T.L",
            "brow.B.R",
            "lid.T.R",
            "forehead.L",
            "forehead.R",
            "forehead.L.001",
            "forehead.R.001",
            "forehead.L.002",
            "forehead.R.002",
            "eye.L",
            "eye.R",
            "cheek.T.L",
            "cheek.T.R",
            "teeth.T",
            "teeth.B",
            "tongue",
            "temple.L",
            "temple.R",
        ]

        for childName in children:
            editBones[childName].parent = editBones["DEF-spine.006"]

        bpy.ops.object.mode_set(mode="OBJECT")

        self.report({"INFO"}, "Finished")
        return {"FINISHED"}  # must return a set


class ToolsPanel(bpy.types.Panel):
    bl_idname = "RIGIFY_GRT_PT_global_tools"
    bl_label = "Rigify GRT Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tool"

    @classmethod
    def poll(cls, context):
        return True

    # called every frame
    def draw(self, context):
        col = self.layout.column()
        col.operator(SetLimbSegments.bl_idname)
        col.operator(SetIKParentsAndGenerateRig.bl_idname)


classes = [SetLimbSegments, SetIKParentsAndGenerateRig, ToolsPanel]


# called on add-on enabling
# register operators and panels here
# append menu layout drawing function to an existing window
def register():
    for cls in classes:
        register_class(cls)


# called on add-on disabling
def unregister():

    for cls in classes:
        unregister_class(cls)
