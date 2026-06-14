#include "clang/AST/ASTContext.h"
#include "clang/AST/Decl.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/AST/Stmt.h"
#include "clang/Basic/Diagnostic.h"
#include "clang/StaticAnalyzer/Checkers/BuiltinCheckerRegistration.h"
#include "clang/StaticAnalyzer/Core/BugReporter/BugReporter.h"
#include "clang/StaticAnalyzer/Core/Checker.h"
#include "clang/StaticAnalyzer/Core/CheckerManager.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/AnalysisManager.h"

#include <vector>

using namespace clang;
using namespace ento;

namespace {

class MISRAC_15_5_Checker : public Checker<check::ASTCodeBody> {
public:
  void checkASTCodeBody(const Decl *D, AnalysisManager &Mgr,
                        BugReporter &BR) const;
};

class MISRAC_15_5_ReturnVisitor
    : public RecursiveASTVisitor<MISRAC_15_5_ReturnVisitor> {
public:
  bool VisitReturnStmt(ReturnStmt *RS) {
    if (RS != nullptr) {
      Returns.push_back(RS);
    }
    return true;
  }

  const std::vector<const ReturnStmt *> &getReturns() const { return Returns; }

private:
  std::vector<const ReturnStmt *> Returns;
};

static const Stmt *stripTransparentStmt(const Stmt *S) {
  while (S != nullptr) {
    if (const AttributedStmt *AS = dyn_cast<AttributedStmt>(S)) {
      S = AS->getSubStmt();
      continue;
    }
    break;
  }
  return S;
}

static const Stmt *getLastNonNullTopLevelStmt(const CompoundStmt *CS) {
  if (CS == nullptr) {
    return nullptr;
  }

  const Stmt *Last = nullptr;

  for (const Stmt *S : CS->body()) {
    if (S == nullptr) {
      continue;
    }

    S = stripTransparentStmt(S);

    if (S == nullptr) {
      continue;
    }

    if (isa<NullStmt>(S)) {
      continue;
    }

    Last = S;
  }

  return Last;
}

static bool isReturnAtFunctionEnd(const FunctionDecl *FD,
                                  const ReturnStmt *RS) {
  if (FD == nullptr || RS == nullptr || !FD->hasBody()) {
    return false;
  }

  const CompoundStmt *Body = dyn_cast<CompoundStmt>(FD->getBody());
  if (Body == nullptr) {
    return false;
  }

  const Stmt *Last = getLastNonNullTopLevelStmt(Body);
  Last = stripTransparentStmt(Last);

  return Last == RS;
}

static void reportRule155(ASTContext &Ctx, SourceLocation Loc,
                          StringRef Message) {
  DiagnosticsEngine &DE = Ctx.getDiagnostics();

  unsigned DiagID = DE.getCustomDiagID(DiagnosticsEngine::Warning,
                                       "MISRA C:2012 Rule 15.5 violation: %0");

  DE.Report(Loc, DiagID) << Message;
}

} // end anonymous namespace

void MISRAC_15_5_Checker::checkASTCodeBody(const Decl *D, AnalysisManager &Mgr,
                                           BugReporter &BR) const {
  (void)BR;

  if (D == nullptr) {
    return;
  }

  const FunctionDecl *FD = dyn_cast<FunctionDecl>(D);
  if (FD == nullptr || !FD->hasBody()) {
    return;
  }

  ASTContext &Ctx = Mgr.getASTContext();

  MISRAC_15_5_ReturnVisitor Visitor;
  Visitor.TraverseStmt(const_cast<Stmt *>(FD->getBody()));

  const std::vector<const ReturnStmt *> &Returns = Visitor.getReturns();

  if (Returns.empty()) {
    return;
  }

  /*
   * MISRA C:2012 Rule 15.5
   * A function should have a single point of exit at the end.
   *
   * This checker reports:
   * 1. More than one return statement in a function.
   * 2. A single return statement that is not the final top-level statement
   *    of the function body.
   */

  if (Returns.size() > 1U) {
    for (const ReturnStmt *RS : Returns) {
      if (RS == nullptr) {
        continue;
      }

      reportRule155(Ctx, RS->getReturnLoc(),
                    "function has more than one exit point");
    }
    return;
  }

  const ReturnStmt *OnlyReturn = Returns.front();

  if (!isReturnAtFunctionEnd(FD, OnlyReturn)) {
    reportRule155(Ctx, OnlyReturn->getReturnLoc(),
                  "the single exit point of a function should be at the end");
  }
}

namespace clang {
namespace ento {

void registerMISRAC_15_5(CheckerManager &Mgr) {
  Mgr.registerChecker<MISRAC_15_5_Checker>();
}

bool shouldRegisterMISRAC_15_5(const CheckerManager &Mgr) { return true; }

} // namespace ento
} // namespace clang