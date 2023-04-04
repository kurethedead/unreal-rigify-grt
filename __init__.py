import bpy
from bpy.utils import register_class, unregister_class

# info about add on
bl_info = {
    "name": "Unreal Rigify To GRT",
    "version": (1, 0, 0),
    "author": "kurethedead",
    "location": "3DView",
    "description": "Automating GRT rig generation from a Rigify metarig for use with Unreal",
    "category": "Armature",
    "blender": (3, 4, 0),
}


class GenerateRig(bpy.types.Operator):
    # set bl_ properties
    bl_description = "Generates a GRT rig from a Rigify metarig"
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

        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.pose.rigify_generate()
        ikRigObj = bpy.context.active_object

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
        constraint.use_z = False

        # Add shape key rig if applicable.
        shapeKeyRig = bpy.context.scene.rigifyToGRTProperty.shapeKeyRig
        if shapeKeyRig:
            childBoneNames = [
                bone.name for bone in shapeKeyRig.data.bones if bone.select
            ]
            bpy.ops.object.select_all(action="DESELECT")
            shapeKeyRig.select_set(True)
            ikRigObj.select_set(True)
            bpy.context.view_layer.objects.active = ikRigObj
            bpy.ops.object.join()

            bpy.ops.object.mode_set(mode="EDIT")
            controlEditBones = ikRigObj.data.edit_bones
            for childBoneName in childBoneNames:
                controlEditBones[childBoneName].parent = controlEditBones["head"]

            # TODO: Handle bone parenting, not all bones should be parented?

        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.gamerigtool.generate_game_rig(Deform_Armature_Name="Armature")
        bpy.ops.object.mode_set(mode="EDIT")

        # Reparent bones on GRT rig so that hierarchy makes sense in Unreal
        # Every bone should be in same hierarchy under the root bone
        GRTRigObj = bpy.context.active_object
        editBones = GRTRigObj.data.edit_bones
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

        for childName in faceBoneNames:
            name = f"DEF-{childName}"
            if name in editBones:
                editBones[name].parent = editBones["DEF-spine.006"]

        bpy.ops.object.mode_set(mode="OBJECT")

        GRTSettings = context.scene.GRT_Action_Bakery_Global_Settings
        GRTSettings.Source_Armature = ikRigObj
        GRTSettings.Target_Armature = GRTRigObj

        metarigObj.hide_set(True)

        self.report({"INFO"}, "Finished")
        return {"FINISHED"}  # must return a set


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
        operator = col.operator(GenerateRig.bl_idname)
        col.prop(prop, "shapeKeyRig")
        col.label(
            text='The selected bones in this rig are parented to the "head" bone in the control rig.'
        )
        col.label(text="Make sure all bones in this rig are deformable.")


def pollShapeKeyRig(self, obj):
    return isinstance(obj.data, bpy.types.Armature)


class RigifyToGRTProperty(bpy.types.PropertyGroup):
    shapeKeyRig: bpy.props.PointerProperty(
        type=bpy.types.Object, poll=pollShapeKeyRig, name="Shape Key Rig"
    )


classes = [GenerateRig, ToolsPanel, RigifyToGRTProperty]


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
