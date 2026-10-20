"""Native click-through window with per-pixel alpha (no color-key edges)."""
import ctypes as c
from ctypes import wintypes as w


class LayeredWindow:
    def __init__(self, width, height):
        self.user = c.WinDLL('user32', use_last_error=True)
        # Keep this drawing thread in physical pixels even when WebView changes
        # the process DPI mode after the indicator has already been created.
        self.user.SetThreadDpiAwarenessContext.argtypes = [c.c_void_p]
        self.user.SetThreadDpiAwarenessContext.restype = c.c_void_p
        self.user.SetThreadDpiAwarenessContext(c.c_void_p(-4))
        self.gdi = c.WinDLL('gdi32', use_last_error=True)
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.width, self.height = width, height
        self.user.CreateWindowExW.restype = w.HWND
        self.user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR,
            w.DWORD, c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU,
            w.HINSTANCE, c.c_void_p]
        self.user.DefWindowProcW.restype = c.c_ssize_t
        self.user.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        self.user.DestroyWindow.argtypes = [w.HWND]
        self.user.GetDC.restype = w.HDC
        self.user.GetDC.argtypes = [w.HWND]
        self.user.ReleaseDC.argtypes = [w.HWND, w.HDC]
        self.user.SetWindowPos.argtypes = [w.HWND, w.HWND, c.c_int, c.c_int,
                                          c.c_int, c.c_int, w.UINT]
        self.gdi.CreateCompatibleDC.restype = w.HDC
        self.gdi.CreateCompatibleDC.argtypes = [w.HDC]
        self.gdi.SelectObject.restype = w.HANDLE
        self.gdi.SelectObject.argtypes = [w.HDC, w.HANDLE]
        self.gdi.DeleteObject.argtypes = [w.HANDLE]
        self.gdi.DeleteDC.argtypes = [w.HDC]
        self.gdi.SetBitmapBits.argtypes = [w.HBITMAP, w.DWORD, c.c_void_p]
        self.gdi.CreateDIBSection.restype = w.HBITMAP
        self.gdi.CreateDIBSection.argtypes = [w.HDC, c.c_void_p, w.UINT,
                                            c.POINTER(c.c_void_p), w.HANDLE, w.DWORD]
        self.kernel.GetModuleHandleW.restype = w.HMODULE
        self.kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
        proc_type = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

        class WindowClass(c.Structure):
            _fields_ = [('style', w.UINT), ('proc', proc_type),
                ('class_extra', c.c_int), ('window_extra', c.c_int),
                ('instance', w.HINSTANCE), ('icon', w.HANDLE),
                ('cursor', w.HANDLE), ('background', w.HANDLE),
                ('menu', w.LPCWSTR), ('name', w.LPCWSTR)]

        def window_proc(hwnd, message, wp, lp):
            if message == 0x0010:  # WM_CLOSE: only the owning application can stop it.
                return 0
            if message == 0x84:  # WM_NCHITTEST: never intercept a click.
                return -1  # HTTRANSPARENT
            if message == 0x21:  # WM_MOUSEACTIVATE
                return 3  # MA_NOACTIVATE
            return self.user.DefWindowProcW(hwnd, message, wp, lp)

        self.proc = proc_type(window_proc)
        instance = self.kernel.GetModuleHandleW(None)
        name = 'WhisperFlowAlphaOverlay'
        wc = WindowClass(0, self.proc, 0, 0, instance, None, None, None, None, name)
        self.user.RegisterClassW.argtypes = [c.POINTER(WindowClass)]
        if not self.user.RegisterClassW(c.byref(wc)):
            raise c.WinError(c.get_last_error())
        self.class_name, self.instance = name, instance
        # Layered + transparent + toolwindow + noactivate. No caption, no drag.
        self.hwnd = self.user.CreateWindowExW(0x080800A0, name, 'WhisperFlow Bar',
            0x80000000, 0, 18, width, height, None, None, instance, None)
        if not self.hwnd:
            raise c.WinError(c.get_last_error())
        self.screen_dc = self.user.GetDC(None)
        self.dc = self.gdi.CreateCompatibleDC(self.screen_dc)
        # BITMAPINFOHEADER: top-down, 32-bit BGRA.
        header = (c.c_uint32 * 10)(40, width, (-height) & 0xffffffff,
                                   (32 << 16) | 1, 0, width * height * 4, 0, 0, 0, 0)
        self.header = header
        self.bits = c.c_void_p()
        self.bitmap = self.gdi.CreateDIBSection(self.dc, c.byref(header), 0,
                                               c.byref(self.bits), None, 0)
        if not self.bitmap or not self.bits.value:
            raise c.WinError(c.get_last_error())
        self.old_bitmap = self.gdi.SelectObject(self.dc, self.bitmap)
        self.user.UpdateLayeredWindow.argtypes = [w.HWND, w.HDC, c.POINTER(w.POINT),
            c.POINTER(w.SIZE), w.HDC, c.POINTER(w.POINT), w.COLORREF,
            c.c_void_p, w.DWORD]
        self.user.PeekMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
        self.user.SetPropW.argtypes = [w.HWND, w.LPCWSTR, w.HANDLE]
        self.frame_sequence = 0
        self.user.ShowWindow.argtypes = [w.HWND, c.c_int]
        self.user.ShowWindow(self.hwnd, 4)

    def present(self, image, opacity=255):
        # Windows requires premultiplied alpha. RGBa performs this conversion.
        self.gdi.GdiFlush()
        if opacity != 255:
            image = image.copy()
            image.putalpha(image.getchannel('A').point(lambda alpha: (alpha * opacity + 127) // 255))
        data = image.convert('RGBa').tobytes('raw', 'BGRa')
        # A fresh DIB gives the compositor a completed frame, rather than
        # mutating the bitmap which it may still be displaying.
        frame_bits = c.c_void_p()
        frame_bitmap = self.gdi.CreateDIBSection(self.dc, c.byref(self.header), 0,
                                                c.byref(frame_bits), None, 0)
        if not frame_bitmap:
            raise c.WinError(c.get_last_error())
        c.memmove(frame_bits, data, len(data))
        previous = self.gdi.SelectObject(self.dc, frame_bitmap)
        work_area = w.RECT()
        if not self.user.SystemParametersInfoW(0x0030, 0, c.byref(work_area), 0):
            raise c.WinError(c.get_last_error())
        x = (work_area.left + work_area.right - self.width) // 2
        y = work_area.bottom - self.height - 12
        dest, source = w.POINT(x, y), w.POINT(0, 0)
        size = w.SIZE(self.width, self.height)
        self.opacity = opacity
        blend = (c.c_ubyte * 4)(0, 0, 255, 1)  # Opacity is baked into per-pixel alpha.
        self.user.SetWindowPos(self.hwnd, w.HWND(-1), x, y,
                              self.width, self.height, 0x0050)
        updated = self.user.UpdateLayeredWindow(self.hwnd, self.screen_dc, c.byref(dest),
                c.byref(size), self.dc, c.byref(source), 0, c.byref(blend), 2)
        self.gdi.SelectObject(self.dc, previous)
        self.gdi.DeleteObject(frame_bitmap)
        if not updated:
            raise c.WinError(c.get_last_error())
        self.gdi.GdiFlush()
        msg = w.MSG()
        self.frame_sequence += 1
        self.user.SetPropW(self.hwnd, 'WhisperFlow.Opacity', w.HANDLE(opacity))
        self.user.SetPropW(self.hwnd, 'WhisperFlow.Frame', w.HANDLE(self.frame_sequence))
        while self.user.PeekMessageW(c.byref(msg), self.hwnd, 0, 0, 1):
            self.user.TranslateMessage(c.byref(msg))
            self.user.DispatchMessageW(c.byref(msg))

    def close(self):
        if getattr(self, 'hwnd', None):
            self.user.DestroyWindow(self.hwnd)
            self.hwnd = None
        if getattr(self, 'dc', None):
            if getattr(self, 'old_bitmap', None):
                self.gdi.SelectObject(self.dc, self.old_bitmap)
            if getattr(self, 'bitmap', None):
                self.gdi.DeleteObject(self.bitmap)
            self.gdi.DeleteDC(self.dc)
            self.dc = None
        if getattr(self, 'screen_dc', None):
            self.user.ReleaseDC(None, self.screen_dc)
            self.screen_dc = None
        if getattr(self, 'class_name', None):
            self.user.UnregisterClassW.argtypes = [w.LPCWSTR, w.HINSTANCE]
            self.user.UnregisterClassW(self.class_name, self.instance)
            self.class_name = None
