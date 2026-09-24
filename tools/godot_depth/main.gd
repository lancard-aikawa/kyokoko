extends Node3D
## 深度付きの写真を 1 ショット分動かす。tools/depth.py が Movie Maker で起動する。
##   godot --path tools/godot_depth --write-movie <out.avi> --fixed-fps 30
##         --quit-after <frames> -- <params.json>
## 書き出しの大きさは project.godot の viewport (1920x1080) で決まる。
## params.json の中身は depth.py の render() を見ること。

var _p: Dictionary
var _cam: Camera3D
var _i := 0


func _ready() -> void:
	_p = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	var dir: String = _p.data_dir

	var photo := Image.load_from_file(dir.path_join("photo.jpg"))
	var meta: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(dir.path_join("depth.json")))
	var depth := Image.create_from_data(
		int(meta.w), int(meta.h), false, Image.FORMAT_RF,
		FileAccess.get_file_as_bytes(dir.path_join("depth.f32")))

	var mat := ShaderMaterial.new()
	mat.shader = load("res://depth_photo.gdshader")
	mat.set_shader_parameter("photo", ImageTexture.create_from_image(photo))
	mat.set_shader_parameter("depth_map", ImageTexture.create_from_image(depth))
	mat.set_shader_parameter("tan_half_h", tan(deg_to_rad(float(_p.hfov) * 0.5)))
	mat.set_shader_parameter("aspect", float(photo.get_width()) / photo.get_height())
	mat.set_shader_parameter("inv_near", 1.0 / float(_p.near))
	mat.set_shader_parameter("inv_far", 1.0 / float(_p.far))

	# 格子は深度マップの半分程度の細かさで足りる
	var plane := PlaneMesh.new()
	plane.subdivide_width = 511
	plane.subdivide_depth = int(511.0 * photo.get_height() / photo.get_width())
	var mesh := MeshInstance3D.new()
	mesh.mesh = plane
	mesh.material_override = mat
	# 頂点をシェーダーで動かすので、既定の AABB だと視錐台カリングで消える
	mesh.custom_aabb = AABB(Vector3(-100, -100, -100), Vector3(200, 200, 200))
	add_child(mesh)

	_cam = Camera3D.new()
	_cam.keep_aspect = Camera3D.KEEP_WIDTH
	_cam.fov = float(_p.view)
	_cam.far = 200.0
	add_child(_cam)
	_place(0)


func _process(_delta: float) -> void:
	_i += 1
	_place(_i)


func _place(i: int) -> void:
	# u はショット全体の進み (0..1)。構図確認では一部だけ描くので u0..u1 を受け取る
	var n: int = max(1, int(_p.frames) - 1)
	var u := lerpf(float(_p.u0), float(_p.u1), clampf(float(i) / n, 0.0, 1.0))
	var e := smoothstep(0.0, 1.0, u)
	# 始点は撮影したカメラそのもの。そこから前進しつつ少しだけ横へずれる。
	# 視線だけを上下させ、カメラの高さは下げない。下げると手前の物が大きく動き、
	# 写真の下端の外が見えてしまう
	_cam.position = Vector3(float(_p.shift) * e, float(_p.rise) * e, -float(_p.dolly) * e)
	_cam.look_at(Vector3(0, float(_p.look) * float(_p.pivot), -float(_p.pivot)))
