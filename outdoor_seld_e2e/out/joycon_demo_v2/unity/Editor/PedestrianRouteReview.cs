#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using UnityEngine;

public static class PedestrianRouteReview
{
    // Verify actual rendered geometry, not just the route metadata.
    public static string Validate(JapaneseStreetscape world)
    {
        var colliders=new List<MeshCollider>();
        foreach(var mf in world.GetComponentsInChildren<MeshFilter>())
        {
            mf.gameObject.layer=29;
            var c=mf.gameObject.AddComponent<MeshCollider>();c.sharedMesh=mf.sharedMesh;colliders.Add(c);
        }
        Physics.SyncTransforms();
        int sidewalk=0,shoulder=0,crossing=0;
        try
        {
            for(int frame=0;frame<=40;frame++)
            {
                float z=world.WalkDirection*world.WalkSpeed*(frame*.25f-5);
                string expected=world.ObserverSurface(z);
                RaycastHit hit;
                if(!Physics.Raycast(new Vector3(0,1.65f,z),Vector3.down,out hit,1.9f,1<<29))throw new Exception("No rendered floor at t="+(frame*.25f));
                string name=hit.collider.gameObject.name;
                if(expected=="crossing")
                {
                    if(name.StartsWith("D/"))throw new Exception("Street furniture obstructs crossing: "+name);
                    crossing++;continue;
                }
                if(name!="R/pavers" && name!="R/shoulder" && name!="R/tactile")
                    throw new Exception("Observer outside pedestrian pavement at t="+(frame*.25f)+": "+name);
                if(name=="R/shoulder")shoulder++;else sidewalk++;
                if(Mathf.Abs(hit.point.y-world.ObserverGroundHeight(z))>.025f)throw new Exception("Observer floor height mismatch at "+z+": "+hit.point.y);
            }
        }
        finally{foreach(var c in colliders)UnityEngine.Object.DestroyImmediate(c);foreach(var mf in world.GetComponentsInChildren<MeshFilter>())mf.gameObject.layer=0;}
        return "sidewalk="+sidewalk+"; shoulder="+shoulder+"; crossing="+crossing;
    }
    public static void ValidateHud()
    {
        foreach(var size in new[]{new Vector2(1920,1080),new Vector2(1280,720),new Vector2(900,600),new Vector2(800,600),new Vector2(640,360),new Vector2(360,640)})
        {
            var p=DemoHudLayout.Calculate(size.x,size.y);
            foreach(var r in new[]{p.main,p.legend,p.state})
                if(r.x<0||r.y<0||r.xMax>size.x||r.yMax>size.y||r.width<1||r.height<1)throw new Exception("HUD exceeds "+size+": "+r);
            if(p.main.Overlaps(p.legend)||p.main.Overlaps(p.state)||p.legend.Overlaps(p.state))throw new Exception("HUD panels overlap at "+size);
        }
    }
}
#endif
