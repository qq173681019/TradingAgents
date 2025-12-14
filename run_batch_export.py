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
    def __init__(self, v=None):
        self._v = v
    def get(self):
        return self._v
    def set(self, v):
        self._v = v
        print(f"[VAR SET] {v}")


def run():
    app = AShareAnalyzerGUI(None)

    # 替换 GUI 相关方法/属性为 stub，以支持无 GUI 的 headless 运行
    app.root = _StubRoot()
    app.progress_msg_var = _StubVar()
    app.analyze_btn = _StubWidget()
    app.chip_btn = _StubWidget()
    app.status_var = _StubVar()
    app.hide_progress = lambda: None
    app.update_results = lambda *args, **kwargs: print("[update_results] skipped")
    app.show_error = lambda msg: print(f"[show_error] {msg}")

    # 一些界面变量
    app.use_choice_data = _StubVar(False)  # False 表示批量流程应直接调用 chip_analyzer
    app.min_score_var = _StubVar(6.0)
    app.stock_type_var = _StubVar("全部")
    app.period_var = _StubVar("综合")
    app.filter_st_var = _StubVar(False)

    # 直接调用内部同步函数，避免线程/GUI 回调
    print("开始运行批量推荐（同步）...")
    app._perform_stock_recommendations_by_type("全部", 'overall')
    print('\n=== 批量导出脚本结束 ===')


if __name__ == '__main__':
    run()
