import sys
from pathlib import Path
sys.path.insert(0, str(Path('/app/src')))
sys.path.insert(0, '/app')
from PIL import Image, ImageDraw, ImageFont
from docnorm.data.loader import load_image
from web import services
import cv2

font = ImageFont.truetype('/app/.tmp_font.ttf', size=30)
ROOT = Path('/app')
OUT = Path('/app/reports/developer_report_assets')

def pil(arr, edge=680):
    h,w = arr.shape[:2]
    s = min(1.0, edge/max(h,w))
    if s<1: arr = cv2.resize(arr,(int(w*s),int(h*s)))
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))

def sheet(samples, out, cols, rectify=False):
    panels=[];labels=[]
    for rel,label in samples:
        loaded=load_image(ROOT/'data/raw_samples'/rel, max_long_edge=900)
        arr=services._limit_long_edge(loaded.image, 900)
        if rectify:
            r,_q,st=services._apply_rectify(arr, 'ppt')
            if st!='ok': r=arr
            panels.append(pil(arr));labels.append(label+' 原图')
            panels.append(pil(r));labels.append('拉正')
            panels.append(pil(services._apply_scan(r)));labels.append('扫描')
        else:
            panels.append(pil(arr));labels.append(label)
    rows=(len(panels)+cols-1)//cols
    cw=max(p.width for p in panels); ch=max(p.height for p in panels)
    canvas=Image.new('RGB',(cols*cw+(cols+1)*10, rows*(ch+42)+(rows+1)*10),'#fbfbf8')
    d=ImageDraw.Draw(canvas)
    for i,(p,lab) in enumerate(zip(panels,labels)):
        r,c=divmod(i,cols)
        x=10+c*(cw+10); y=10+r*(ch+42+10)
        canvas.paste(p,(x+(cw-p.width)//2, y+(ch-p.height)//2))
        tb=d.textbbox((0,0),lab,font=font); tw=tb[2]-tb[0]
        d.text((x+(cw-tw)//2, y+ch+6), lab, fill='#1f3a5f', font=font)
    canvas.save(OUT/out, quality=90)
    print('saved', out, canvas.size)

if __name__ == '__main__':
    ppt=[("01_ppt_text/IMG_6013.JPG","部署模式"),("01_ppt_text/IMG_6194.JPG","ThreeSpace"),("01_ppt_text/IMG_6233.jpg","文字表格"),("02_ppt_formula/IMG_6209.jpeg","基本概念")]
    sheet(ppt,'tmp_ppt_scan_sheet.jpg',3,rectify=True)
    paper=[("03_paper_text/text_07.jpg","英文讲义"),("03_paper_text/IMG_20261125_232543.jpg","桌面论文"),("03_paper_text/IMG20261126013537.jpg","课堂笔记"),("04_paper_formula/formula_09.jpg","打印公式"),("04_paper_formula/formula_05.jpg","公式讲义"),("04_paper_formula/IMG_20261126_013718.jpg","手写公式")]
    sheet(paper,'tmp_paper_sheet.jpg',3,rectify=False)
