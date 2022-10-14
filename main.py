import os
import copy
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from zaber_motion import Library
from zaber_motion import LogOutputMode
from zaber_motion.binary import Connection
from zaber_motion import Units  # 実世界の単位に変換するため
from DS102Controller import MySerial, DS102Controller
from CustomTkObject import MovableOval, MovableRect
from ConfigLoader import ConfigLoader

# ライブラリをオフラインで使えるようにする
Library.enable_device_db_store()
# ログを取る
Library.set_log_output(LogOutputMode.FILE, "motion_library_log.txt")

WIDTH_BUTTON = 7
SIZE_CANVAS = 400
SIZE_CONT = 15
DT = 200
FONT = ('游ゴシック', 16)
MAX_Z = 25400.032
VEL_LIST_XY = (0, 1, 10, 100, 1000)
VEL_LIST_Z = (0, 0.5, 1, 10, 100, 1000)


def get_color_by_float(value: float):
    codes = ['#222', '#333', '#444', '#555', '#666', '#777', '#888', '#999', '#aaa', '#bbb', '#ccc',
             '#ddd', '#eee', '#fff']
    value *= len(codes)
    for i, color in enumerate(codes):
        if value < i:
            return color


class Application(tk.Frame):
    def __init__(self, master=None, device_xy: DS102Controller=None, device_z=None, cl: ConfigLoader =None):
        super().__init__(master)
        self.master.title('Z Stage Controller')
        self.device_xy = device_xy
        self.device_z = device_z

        # フォントサイズの調整
        self.style = ttk.Style()
        if os.name == 'nt':
            self.style.theme_use('winnative')  # windowsにしかないテーマ
        self.style.configure('.', font=FONT)
        self.style.configure("stop.TButton", background='red', foreground='white')

        self.create_widgets()

        if cl is not None:
            self.dt = cl.dt
        else:
            self.dt = DT

        self.unit_pos = Units.LENGTH_MICROMETRES
        self.unit_vel = Units.VELOCITY_MICROMETRES_PER_SECOND

        self.rank_xy_pre = 0
        self.rank_z_pre = 0

        self.direction_xy_pre = [0, 0, 0]
        self.direction_z_pre = [0, 0, 0]

        self.update()

    def create_widgets(self):
        # 親フレーム
        self.frame_xy = ttk.Frame(self.master)
        self.frame_z = ttk.Frame(self.master)
        self.frame_xy.grid(row=0, column=0)
        self.frame_z.grid(row=0, column=1)
        # 子フレーム
        self.frame_xy_canvas = ttk.Frame(self.frame_xy)
        self.frame_xy_buttons = ttk.Frame(self.frame_xy)
        self.frame_xy_position = ttk.Frame(self.frame_xy)
        self.frame_z_canvas = ttk.Frame(self.frame_z)
        self.frame_z_buttons = ttk.Frame(self.frame_z)
        self.frame_z_position = ttk.Frame(self.frame_z)
        self.frame_xy_canvas.grid(row=0, column=0, columnspan=2)
        self.frame_xy_buttons.grid(row=1, column=0)
        self.frame_xy_position.grid(row=2, column=0)
        self.frame_z_canvas.grid(row=0, column=0, columnspan=2)
        self.frame_z_buttons.grid(row=1, column=0)
        self.frame_z_position.grid(row=2, column=0)
        # ウィジェット xy_canvas
        self.canvas_xy = tk.Canvas(self.frame_xy_canvas, width=SIZE_CANVAS, height=SIZE_CANVAS)
        center = SIZE_CANVAS/2
        r_list = [SIZE_CONT*9, SIZE_CONT*7, SIZE_CONT*5, SIZE_CONT*3, SIZE_CONT*1]
        for i, r in enumerate(r_list):
            color = get_color_by_float(i / len(r_list))
            self.canvas_xy.create_oval(center - r, center - r, center + r, center + r, fill=color)
        MovableOval.canvas = self.canvas_xy
        MovableOval.thres_list = r_list
        self.oval_xy = MovableOval(center-SIZE_CONT, center-SIZE_CONT, center+SIZE_CONT, center+SIZE_CONT, fill='lightblue')
        self.canvas_xy.pack()
        # ウィジェット xy_buttons
        self.vel_xy = tk.IntVar(value=100)
        self.combobox_xy = ttk.Combobox(self.frame_xy_buttons, values=VEL_LIST_XY[1:], textvariable=self.vel_xy, justify='center', width=WIDTH_BUTTON)
        self.button_top = ttk.Button(self.frame_xy_buttons, width=WIDTH_BUTTON, text='↑', command=self.move_top)
        self.button_left = ttk.Button(self.frame_xy_buttons, width=WIDTH_BUTTON, text='←', command=self.move_left)
        self.button_right = ttk.Button(self.frame_xy_buttons, width=WIDTH_BUTTON, text='→', command=self.move_right)
        self.button_bottom = ttk.Button(self.frame_xy_buttons, width=WIDTH_BUTTON, text='↓', command=self.move_bottom)
        self.button_top.grid(row=0, column=1)
        self.button_left.grid(row=1, column=0)
        self.combobox_xy.grid(row=1, column=1)
        self.button_right.grid(row=1, column=2)
        self.button_bottom.grid(row=2, column=1)
        # ウィジェット xy_position
        self.x_cur = tk.DoubleVar(value=0)
        self.y_cur = tk.DoubleVar(value=0)
        self.label_x = ttk.Label(self.frame_xy_position, text='X [\u03bcm]')
        self.label_y = ttk.Label(self.frame_xy_position, text='Y [\u03bcm]')
        self.label_x_cur = ttk.Label(self.frame_xy_position, textvariable=self.x_cur)
        self.label_y_cur = ttk.Label(self.frame_xy_position, textvariable=self.y_cur)
        self.label_x.grid(row=0, column=0)
        self.label_x_cur.grid(row=0, column=1)
        self.label_y.grid(row=1, column=0)
        self.label_y_cur.grid(row=1, column=1)
        # ウィジェット z_canvas
        self.canvas_z = tk.Canvas(self.frame_z_canvas, width=SIZE_CANVAS/2, height=SIZE_CANVAS)
        xmin = SIZE_CANVAS * 0.1
        xmax = SIZE_CANVAS * 0.4
        y_list = [SIZE_CONT*11, SIZE_CONT*9, SIZE_CONT*7, SIZE_CONT*5, SIZE_CONT*3, SIZE_CONT*1]
        for i, y in enumerate(y_list):
            color = get_color_by_float(i / len(y_list))
            self.canvas_z.create_rectangle(xmin, SIZE_CANVAS/2-y, xmax, SIZE_CANVAS/2+y, fill=color)
        MovableRect.canvas = self.canvas_z
        MovableRect.thres_list = y_list
        self.rect_z = MovableRect(xmin, SIZE_CANVAS/2-SIZE_CONT, xmax, SIZE_CANVAS/2+SIZE_CONT, fill='lightblue')
        self.canvas_z.pack()
        # ウィジェット z_buttons
        self.vel_z = tk.IntVar(value=100)
        self.combobox_z = ttk.Combobox(self.frame_z_buttons, values=VEL_LIST_Z[1:], textvariable=self.vel_z, justify='center', width=WIDTH_BUTTON)
        self.button_up = ttk.Button(self.frame_z_buttons, width=WIDTH_BUTTON, text='UP', command=self.move_up)
        self.button_down = ttk.Button(self.frame_z_buttons, width=WIDTH_BUTTON, text='DOWN', command=self.move_down)
        self.button_up.grid(row=0, column=0)
        self.combobox_z.grid(row=1, column=0)
        self.button_down.grid(row=2, column=0)
        # ウィジェット z_position
        self.z_cur = tk.DoubleVar(value=0)
        self.label_z = ttk.Label(self.frame_z_position, text='Z [\u03bcm]')
        self.label_z_cur = ttk.Label(self.frame_z_position, textvariable=self.z_cur)
        self.label_z.grid(row=0, column=0)
        self.label_z_cur.grid(row=0, column=1)

        self.button_stop = ttk.Button(self.master, text='STOP', command=self.stop_all, style='stop.TButton')
        self.button_stop.grid(row=2, columnspan=2)
        self.msg = tk.StringVar(value='Ready')
        self.label_msg = ttk.Label(self.master, textvariable=self.msg)
        self.label_msg.grid(columnspan=2)

    def update(self):
        self.msg.set(f'oval:\t{self.oval_xy.get_rank()} {self.oval_xy.get_direction()}\n'
                     f'rect:\t{self.rect_z.get_rank()} {self.rect_z.get_direction()}')
        self.check_and_move()
        self.check_and_stop()
        self.update_position()
        self.rank_xy_pre = self.oval_xy.get_rank()
        self.rank_z_pre = self.rect_z.get_rank()
        self.direction_xy_pre = copy.copy(self.oval_xy.get_direction())
        self.direction_z_pre = copy.copy(self.rect_z.get_direction())
        self.master.after(self.dt, self.update)

    def check_and_move(self):
        # 図形から操作された場合を検知
        # XY方向
        if self.rank_xy_pre != self.oval_xy.get_rank() or self.direction_xy_pre != self.oval_xy.get_direction():
            if self.oval_xy.direction[0] > 0:
                self.move_right()
            elif self.oval_xy.direction[0] < 0:
                self.move_left()
            if self.oval_xy.direction[1] > 0:
                self.move_top()
            elif self.oval_xy.direction[1] < 0:
                self.move_bottom()
        # Z方向
        if self.rank_z_pre != self.rect_z.get_rank() or self.direction_z_pre != self.rect_z.get_direction():
            if self.rect_z.direction[2] > 0:
                self.move_up()
            elif self.rect_z.direction[2] < 0:
                self.move_down()

    def check_and_stop(self):
        # 前回までは動く命令、今回止まる命令が出ていればstopを呼び出す
        if self.rank_xy_pre != 0 and self.oval_xy.get_rank() == 0:
            self.stop_xy()
        if self.rank_z_pre != 0 and self.rect_z.get_rank() == 0:
            self.stop_z()

    def move_up(self):
        # rank==0→ボタンから呼ばれた
        if self.rect_z.get_rank() > 0:
            vel = VEL_LIST_Z[self.rect_z.get_rank()]
            print('move up by upper')
        else:
            vel = self.vel_z.get()
            print('move up by downer')
        if self.device_z is None:
            print(f'move up by {vel} \u03bcm/s')
        else:
            self.device_z.move_velocity(vel, unit=self.unit_vel)

    def move_down(self):
        # rank==0→ボタンから呼ばれた
        if self.rect_z.get_rank() > 0:
            vel = -VEL_LIST_Z[self.rect_z.get_rank()]
            print('move down by upper')
        else:
            vel = -self.vel_z.get()
            print('move down by downer')

        if self.device_z is None:
            print(f'move down by {vel} \u03bcm/s')
        else:
            self.device_z.move_velocity(vel, unit=self.unit_vel)

    def move_right(self):
        # rank==0→ボタンから呼ばれた
        if self.oval_xy.get_rank() > 0:
            vel = VEL_LIST_XY[self.oval_xy.get_rank()]
            print('move right by upper')
        else:
            vel = self.vel_xy.get()
            print('move right by downer')

        if self.device_xy is None:
            print(f'move right by {vel} \u03bcm/s')
        else:
            self.device_xy.move_velocity('x', vel)

    def move_left(self):
        # rank==0→ボタンから呼ばれた
        if self.oval_xy.get_rank() > 0:
            vel = -VEL_LIST_XY[self.oval_xy.get_rank()]
            print('move left by upper')
        else:
            vel = -self.vel_xy.get()
            print('move left by downer')

        if self.device_xy is None:
            print(f'move left by {vel} \u03bcm/s')
        else:
            self.device_xy.move_velocity('x', vel)

    def move_top(self):
        # rank==0→ボタンから呼ばれた
        if self.oval_xy.get_rank() > 0:
            vel = VEL_LIST_XY[self.oval_xy.get_rank()]
            print('move top by upper')
        else:
            vel = self.vel_xy.get()
            print('move top by downer')

        if self.device_xy is None:
            print(f'move top by {vel} \u03bcm/s')
        else:
            self.device_xy.move_velocity('y', vel)

    def move_bottom(self):
        # rank==0→ボタンから呼ばれた
        if self.oval_xy.get_rank() > 0:
            vel = -VEL_LIST_XY[self.oval_xy.get_rank()]
            print('move bottom by upper')
        else:
            vel = -self.vel_xy.get()
            print('move bottom by downer')

        if self.device_xy is None:
            print(f'move bottom by {vel} \u03bcm/s')
        else:
            self.device_xy.move_velocity('y', vel)

    def stop_xy(self):
        if self.device_xy is None:
            print('stop xy')
        else:
            self.device_xy.stop()

    def stop_z(self):
        if self.device_z is None:
            print('stop z')
        else:
            self.device_z.stop()

    def stop_all(self):
        self.stop_xy()
        self.stop_z()

    def update_position(self):
        if self.device_xy is None or self.device_z is None:
            return
        x, y = self.device_xy.get_position()
        z = MAX_Z - self.device_z.get_position(unit=self.unit_pos)
        self.x_cur.set(x)
        self.y_cur.set(y)
        self.z_cur.set(z)


def main():
    cl = ConfigLoader('./config.json')

    if cl.mode == 'DEBUG':
        main_debug(cl)
    elif cl.mode == 'RELEASE':
        main_release(cl)

def main_debug(cl):
    root = tk.Tk()
    # こうしないとコンボボックスのフォントが変わらない
    root.option_add("*font", FONT)
    # ウィンドウを閉じる際のイベント
    def on_closing():
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    app = Application(master=root, device_z=None, cl=cl)
    app.mainloop()

def main_release(cl):
    with MySerial(cl.port_xy, cl.baudrate_xy) as ser:
        device_xy = DS102Controller(ser)
        with Connection.open_serial_port(cl.port_z) as connection:
            device_list = connection.detect_devices()
            device_z = device_list[0]

            root = tk.Tk()
            # こうしないとコンボボックスのフォントが変わらない
            root.option_add("*font", FONT)
            # ウィンドウを閉じる際のイベント
            def on_closing():
                if messagebox.askokcancel('警告', '自動で定位置へと移動します。よろしいですか？'):
                    root.destroy()
            root.protocol("WM_DELETE_WINDOW", on_closing)
            app = Application(master=root, device_xy=device_xy, device_z=device_z, cl=cl)
            app.mainloop()

        device_z.move_absolute(9000, unit=Units.LENGTH_MICROMETRES)

    print('Successfully finished the controller program.')

if __name__ == '__main__':
    main()
