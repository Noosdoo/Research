using UnityEngine;

// All IMGUI panels use one layout so small windows cannot overlap or overflow.
public static class DemoHudLayout
{
    public struct Panels { public Rect main,legend,state; }
    public static Panels Calculate(float width,float height)
    {
        float pad=Mathf.Min(12,width*.025f),gap=8;
        float stateHeight=Mathf.Clamp(height*.12f,36,64);
        Rect state=new Rect(pad,height-pad-stateHeight,width-2*pad,stateHeight);
        bool wide=width>=900;
        float legendHeight=Mathf.Clamp(height*.24f,80,152);
        float legendWidth=wide?Mathf.Min(360,width*.36f):width-2*pad;
        Rect legend=new Rect(width-pad-legendWidth,state.y-gap-legendHeight,legendWidth,legendHeight);
        Rect main=new Rect(pad,pad,wide?Mathf.Min(460,width*.40f):width-2*pad,(wide?state.y:legend.y)-gap-pad);
        main.height=Mathf.Max(48,main.height);
        return new Panels{main=main,legend=legend,state=state};
    }
    public static Panels Current { get { return Calculate(Screen.width,Screen.height); } }
    public static void Background(Rect rect)
    {Color old=GUI.color;GUI.color=new Color(.035f,.055f,.05f,.82f);GUI.DrawTexture(rect,Texture2D.whiteTexture);GUI.color=old;}
    public static bool MouseOverPanel()
    {
        Vector2 p=new Vector2(Input.mousePosition.x,Screen.height-Input.mousePosition.y);var rects=Current;
        return rects.main.Contains(p)||rects.legend.Contains(p)||rects.state.Contains(p);
    }
    public static void TextPanel(Rect rect,string text,GUIStyle style,ref Vector2 scroll)
    {
        Background(rect);float width=rect.width-30;
        float h=style.CalcHeight(new GUIContent(text),width)+12;
        scroll=GUI.BeginScrollView(rect,scroll,new Rect(0,0,width+12,Mathf.Max(rect.height-1,h)),false,h>rect.height);
        GUI.Label(new Rect(8,6,width,h-12),text,style);GUI.EndScrollView();
    }
}
