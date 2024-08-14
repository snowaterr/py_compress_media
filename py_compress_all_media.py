import os
import subprocess
import re
import exiftool
from PIL import Image
from datetime import datetime
import traceback

# 图片分辨率超过下面设定的，会自动缩小分辨率，但比例不变  //////////  -1表示尺寸不变
max_size_x = 3024
max_size_y = 3024
# max_size_x = -1
# max_size_y = -1
#文件路径，会包括其子文件夹
path = "."

#将压缩的图片的格式
to_compress_image_formats = ['jpg','png','jpeg']
#将压缩的视频格式
to_compress_vedio_formats = ['mov','mp4']
#要删除的格式
to_delete_formats = ['aae']


# region Function
metadataTags = [        # 要复制的元数据类型
    'EXIF:Make',  
    'EXIF:Model',  
    'EXIF:Software',  
    'EXIF:Orientation',
    'EXIF:XResolution',
    'EXIF:YResolution',
    'EXIF:ResolutionUnit',
    'EXIF:ModifyDate',  
    'EXIF:HostComputer',  
    'EXIF:ExposureTime',  
    'EXIF:FNumber',  
    'EXIF:ExposureProgram',
    'EXIF:ISO',
    'EXIF:DateTimeOriginal',  
    'EXIF:CreateDate',  
    'EXIF:OffsetTime',  
    'EXIF:OffsetTimeOriginal',  
    'EXIF:OffsetTimeDigitized',  
    'EXIF:ShutterSpeedValue',  
    'EXIF:ApertureValue',  
    'EXIF:BrightnessValue',  
    'EXIF:ExposureCompensation', 
    'EXIF:MeteringMode',  
    'EXIF:Flash',  
    'EXIF:FocalLength',  
    'EXIF:SubSecTimeOriginal',  
    'EXIF:SubSecTimeDigitized',  
    'EXIF:ExposureMode',
    'EXIF:WhiteBalance',
    'EXIF:ColorSpace',
    # 'EXIF:ExifImageWidth',
    # 'EXIF:ExifImageHeight',
    'EXIF:FocalLengthIn35mmFormat',
    'EXIF:LensInfo',
    'EXIF:LensMake',
    'EXIF:LensModel',  
    'EXIF:CompositeImage',
    'EXIF:GPSLatitudeRef',
    'EXIF:GPSLatitude',
    'EXIF:GPSLongitudeRef',
    'EXIF:GPSLongitude',
    'EXIF:GPSAltitudeRef',
    'EXIF:GPSAltitude',
    'EXIF:GPSTimeStamp',
    'EXIF:GPSSpeedRef',
    'EXIF:GPSSpeed',
    'EXIF:GPSImgDirectionRef',
    'EXIF:GPSImgDirection',
    'EXIF:GPSDestBearingRef',
    'EXIF:GPSDestBearing',
    'EXIF:GPSDateStamp',
    'EXIF:GPSHPositioningError',
    'EXIF:Compression',
    'EXIF:Artist',
    'EXIF:Copyright',
    ]

def extract_metadata(input_file):
    try:
        with exiftool.ExifToolHelper() as et:
            metadata = et.get_tags([input_file], tags=metadataTags)[0]
            params = et.get_tags([input_file], tags=['EXIF:Orientation','File:ImageWidth','File:ImageHeight'])[0]
            return metadata, params['EXIF:Orientation'], params['File:ImageWidth'], params['File:ImageHeight']
        
    except Exception:
        with Image.open(input_file) as img:
            width, height = img.size
            return {}, 1, width, height

def write_metadata(output_file, metadata):
    try:
        with exiftool.ExifToolHelper() as et:
            et.set_tags(
                [output_file],
                tags=metadata,
                params=["-P", "-overwrite_original"]
            )
    except Exception:
        return

# 这里是反向操作！！用来抵消ffmpeg对旋转的修正
def get_anti_transpose(orientation):
    orientation_map = {
        1: "",          # 正常（不旋转）
        2: "hflip",     # 水平翻转
        3: "transpose=1,transpose=1",  # 旋转 180 度
        4: "vflip",     # 垂直翻转
        5: "transpose=3",  # 顺时针旋转 90 度并垂直翻转
        6: "transpose=2",  # 顺时针旋转 90 度
        7: "transpose=0",  # 逆时针旋转 90 度并垂直翻转
        8: "transpose=1"   # 逆时针旋转 90 度
    }
    return orientation_map.get(orientation, "")

def get_video_duration(input_path):
    # 获取视频总时长
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
    return float(result.stdout)

def run_ffmpeg(ffmpeg_command, input_path, isVedio):
    # 启动ffmpeg进程
    process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', text=True)
    
    if isVedio:
        # 用于解析进度的正则表达式
        progress_pattern = re.compile(r"time=(\d+:\d+:\d+\.\d+)")

        total_duration = get_video_duration(input_path)
        while True:
            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                progress_match = progress_pattern.search(output)
                if progress_match:
                    time_str = progress_match.group(1)
                    # 将时间字符串转换为秒数
                    h, m, s = map(float, time_str.split(':'))
                    current_time = h * 3600 + m * 60 + s
                    progress = (current_time / total_duration) * 100
                    print(f"\rffmpeg convert: {input_path}, progress: {progress:.2f}%", end = "")
        print("")
    else:
        print(f"ffmpeg convert: {input_path}")
        
    stdout, stderr = process.communicate()      # 读取输出和错误流
    # 检查退出状态码
    if process.returncode != 0:
        print("\033[91m\nConversion failed!\n\033[0m")

def compress_image(input_path, output_path):
    # 获得元数据
    meta, orientation, original_width, original_height = extract_metadata(input_path)
    # 获取图像的原始分辨率
    transpose = get_anti_transpose(orientation)

    # 分辨率太大则按比例缩小
    if max_size_x<=0 or max_size_y<=0:
        scale = 1
    else:
        scale = min(1, max_size_x/original_width, max_size_y/original_height)
        scale = 1 if scale <= 0.7 else scale        #长图或者全景图不调分辨率
    new_width = scale * original_width
    new_height = scale * original_height

    # 压缩值
    if(new_height * new_width > 3000000):
        compressValue = '5'
    else:
        compressValue = '2'
    
    if transpose != "":
        transpose += ","
    # 构造ffmpeg命令
    ffmpeg_command = [
        'ffmpeg', '-i', input_path,
        '-q:v', compressValue,
        '-vf', f'{transpose}scale={new_width}:{new_height}',
        '-map_metadata', '0',
        '-y',
        output_path
    ]

    # 执行ffmpeg命令
    run_ffmpeg(ffmpeg_command, input_path, False)

    return meta

def compress_video(input_path, output_path):
    # 构造ffmpeg命令
    ffmpeg_command = [
        'ffmpeg', '-i', input_path,
        '-c:v', 'libx265',
        '-pix_fmt', 'yuv420p',
        '-crf', '23',
        '-c:a', 'aac',
        '-map_metadata', '0',
        '-y',
        output_path
    ]

     # 执行ffmpeg命令
    run_ffmpeg(ffmpeg_command, input_path, True)

def delete_file(input_path):
    os.remove(input_path)
    print(f'\nRemove {input_path}')

def process_media(filename):
    format = filename.split('.')[-1].lower()
    if format in to_delete_formats:
        delete_file(filename)

    elif format in to_compress_image_formats:
        # 转换，并删除原图
        if format == 'jpg':
            output_path = filename
            metadata = compress_image(filename, output_path)
            write_metadata(output_path, metadata)
        else:
            output_path = filename.rsplit('.', 1)[0] + '.jpg'
            metadata = compress_image(filename, output_path)
            write_metadata(output_path, metadata)
            os.remove(filename)

    elif format in to_compress_vedio_formats:
        # 转换，保留原格式，并直接覆盖
        output_path = filename.rsplit('.', 1)[0]+"_.mov"
        compress_video(filename, output_path)
        os.remove(filename)

def process_media_in_folder(folder_path):
    # 用绝对路径
    folder_path = os.path.abspath(folder_path)
    for root, _, files in os.walk(folder_path):
        os.chdir(os.path.join(folder_path, root))
        print(f"\n[ directory: {root} ]")
        for filename in files:
            try:
                process_media(filename)
            except Exception as e:
                tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
                print(f"\033[91m\n{os.path.join(root, filename)} process error, exception: {e}\nTraceback:\n{tb_str}\033[0m")
    
# endregion

def Hint():
    print('''
        自动压缩脚本所在文件夹下所有图片和视频，图片全部压缩为jpg，视频格式不变
        顺便清理.aae文件
        单线程运行，懒得写多线程
        警告：该脚本会自动覆盖原文件！！！文件元数据部分保留(拍摄设备、GPD、时间戳、旋转信息等),一旦覆盖不可撤回
        ''')
    user_input = input("是否继续运行程序？(Y/N): ").strip().lower()
    if user_input.lower() == 'y':
        return True
    else:
        print("程序已终止...")
        return False


if "__main__" == __name__:
    if Hint():
        process_media_in_folder(path)
        print('\ndone...')