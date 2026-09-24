// 写真を「撮影したカメラから見た奥行きのある面」に戻す。
// 原点・-Z 向きのカメラから見ると元の写真と一致し、カメラを動かしたときだけ視差が出る。
// 写っていない面は作らない。境界は引き伸ばされるだけなので、動きを小さく保つこと。
shader_type spatial;
render_mode unshaded, cull_disabled;

uniform sampler2D photo : source_color, filter_linear_mipmap;
uniform sampler2D depth_map : filter_linear;
uniform float tan_half_h = 0.577;  // 写真の水平画角の半分の tan
uniform float aspect = 1.333;      // 写真の幅 / 高さ
uniform float inv_near = 0.5;      // 視差 1 (最も近い) の距離の逆数
uniform float inv_far = 0.03;      // 視差 0 (最も遠い) の距離の逆数

void vertex() {
	float d = textureLod(depth_map, UV, 0.0).r;
	float z = 1.0 / mix(inv_far, inv_near, d);
	vec2 ndc = vec2(UV.x * 2.0 - 1.0, 1.0 - UV.y * 2.0);
	VERTEX = vec3(ndc.x * tan_half_h, ndc.y * tan_half_h / aspect, -1.0) * z;
}

void fragment() {
	ALBEDO = texture(photo, UV).rgb;
}
