from a_share_gui_compatible import AShareAnalyzerGUI


class _StubRoot:
	def after(self, delay, func, *args, **kwargs):
		try:
			func(*args)
		except TypeError:
			func()


class _StubWidget:
	def config(self, *args, **kwargs):
		return None


class _StubVar:
	def set(self, v):
		print(f"[progress_msg_var] {v}")


def run():
	# 创建实例但提供 None root 会跳过 UI 初始化
	app = AShareAnalyzerGUI(None)

	# 替换可能被调用的 GUI 相关方法/属性为 stub，以支持无 GUI 的 headless 运行
	app.root = _StubRoot()
	app.progress_msg_var = _StubVar()
	app.analyze_btn = _StubWidget()
	app.chip_btn = _StubWidget()
	app.status_var = _StubVar()
	app.hide_progress = lambda: None
	app.update_results = lambda *args, **kwargs: print("[update_results] skipped")
	app.show_error = lambda msg: print(f"[show_error] {msg}")
	# UI 中部分变量（如 use_choice_data）在无 GUI 初始化时不存在，创建简单 stub
	class _BoolVarStub:
		def __init__(self, v=False):
			self._v = v
		def get(self):
			return self._v
		def set(self, v):
			self._v = v

	app.use_choice_data = _BoolVarStub(False)

	# 运行单只分析（同步）
	app.perform_analysis('600273')
	print('\n=== 分析脚本结束 ===')


if __name__ == '__main__':
	run()
