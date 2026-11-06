using System;
using System.IO;
using SolidWorks.Interop.sldworks;
public static class HatchStates {
 public static void Setup(IModelDoc2 m,ISldWorks sw) {
  IAssemblyDoc ass=(IAssemblyDoc)m;IComponent2 closed=null,opened=null;
  m.ShowConfiguration2("Default");
  foreach(IComponent2 c in (object[])ass.GetComponents(false))if(c.GetPathName().EndsWith("ED-003_hatch_A.SLDPRT",StringComparison.OrdinalIgnoreCase)) {
   if(closed==null)closed=c;else if(opened==null)opened=c;else throw new Exception("More than two hatch state instances");
  }
  if(opened!=null && opened.GetID()<closed.GetID()){IComponent2 swap=opened;opened=closed;closed=swap;}
  if(closed==null)throw new Exception("Hatch missing");
  closed.SetSuppression2(2);
  if(opened==null)opened=ass.AddComponent5(closed.GetPathName(),0,"",false,"",0,0,0);
  if(opened==null)throw new Exception("Open-state hatch insertion failed");
  int closedID=closed.GetID(),openID=opened.GetID();
  double[][] poses={new double[]{1,0,0,0,1,0,0,0,1,0,0,.0387,1,0,0,0},new double[]{0,1,0,-1,0,0,0,0,1,.0205,.0205,.0387,1,0,0,0}};
  int i=0;foreach(IComponent2 c in new[]{closed,opened}) {
   c.SetSuppression2(2);m.ClearSelection2(true);c.Select4(false,null,false);ass.UnfixComponent();
   c.SetTransformAndSolve2((MathTransform)((IMathUtility)sw.GetMathUtility()).CreateTransform(poses[i++]));
   m.ClearSelection2(true);c.Select4(false,null,false);ass.FixComponent();
  }
  bool hasOpen=false;foreach(string n in (string[])m.GetConfigurationNames())if(n=="Hatch_open_90")hasOpen=true;
  if(!hasOpen)m.AddConfiguration3("Hatch_open_90","Open rotary hatch","",0);
  foreach(string config in new[]{"Default","Hatch_open_90"}) {
   m.ShowConfiguration2(config);
   foreach(IComponent2 c in (object[])ass.GetComponents(false)) {
    bool isOpen=c.GetID()==openID;bool isClosed=c.GetID()==closedID;
    if(!isOpen&&!isClosed)continue;
    bool suppress=isOpen?(config=="Default"):(config!="Default");
    c.SetSuppression2(suppress?0:2);
    if(c.IsSuppressed()!=suppress)throw new Exception("Suppression mismatch "+config+" "+c.Name2);
   }
   m.ForceRebuild3(false);int e=0,w=0;m.Save3(1,ref e,ref w);if(e!=0)throw new Exception("Hatch state save "+e);
  }
  m.ShowConfiguration2("Default");
 }
}
