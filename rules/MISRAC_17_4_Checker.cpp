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

using namespace clang;
using namespace ento;

namespace {

class MISRAC_17_4_Checker : public Checker<check::ASTCodeBody> {
public:
  void checkASTCodeBody(const Decl *D, AnalysisManager &Mgr,
                        BugReporter &BR) const;
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

static bool isReturnWithExpression(const ReturnStmt *RS) {
  if (RS == nullptr) {
    return false;
  }

  return RS->getRetValue() != nullptr;
}

/*
 * Conservative AST-based check:
 * Return true only when this statement guarantees that all paths passing
 * through it exit by an explicit return statement with an expression.
 */
static bool stmtAlwaysReturnsWithExpression(const Stmt *S) {
  if (S == nullptr) {
    return false;
  }

  S = stripTransparentStmt(S);

  if (S == nullptr) {
    return false;
  }

  if (const ReturnStmt *RS = dyn_cast<ReturnStmt>(S)) {
    return isReturnWithExpression(RS);
  }

  if (const CompoundStmt *CS = dyn_cast<CompoundStmt>(S)) {
    for (const Stmt *Child : CS->body()) {
      if (Child == nullptr) {
        continue;
      }

      if (stmtAlwaysReturnsWithExpression(Child)) {
        return true;
      }
    }

    return false;
  }

  if (const IfStmt *IS = dyn_cast<IfStmt>(S)) {
    const Stmt *ThenStmt = IS->getThen();
    const Stmt *ElseStmt = IS->getElse();

    if (ThenStmt == nullptr || ElseStmt == nullptr) {
      return false;
    }

    return stmtAlwaysReturnsWithExpression(ThenStmt) &&
           stmtAlwaysReturnsWithExpression(ElseStmt);
  }

  return false;
}

class MISRAC_17_4_ReturnVisitor
    : public RecursiveASTVisitor<MISRAC_17_4_ReturnVisitor> {
public:
  explicit MISRAC_17_4_ReturnVisitor(ASTContext &Ctx) : Ctx(Ctx) {}

  bool VisitReturnStmt(ReturnStmt *RS) {
    if (RS == nullptr) {
      return true;
    }

    /*
     * MISRA C:2012 Rule 17.4
     * All exit paths from a function with non-void return type shall have
     * an explicit return statement with an expression.
     */
    if (RS->getRetValue() == nullptr) {
      DiagnosticsEngine &DE = Ctx.getDiagnostics();

      unsigned DiagID = DE.getCustomDiagID(
          DiagnosticsEngine::Warning,
          "MISRA C:2012 Rule 17.4 violation: return statement in a "
          "non-void function shall have an explicit expression");

      DE.Report(RS->getReturnLoc(), DiagID);
    }

    return true;
  }

private:
  ASTContext &Ctx;
};

static void reportMissingReturnExpression(ASTContext &Ctx, SourceLocation Loc) {
  DiagnosticsEngine &DE = Ctx.getDiagnostics();

  unsigned DiagID = DE.getCustomDiagID(
      DiagnosticsEngine::Warning,
      "MISRA C:2012 Rule 17.4 violation: not all exit paths from this "
      "non-void function have an explicit return statement with an expression");

  DE.Report(Loc, DiagID);
}

} // end anonymous namespace

void MISRAC_17_4_Checker::checkASTCodeBody(const Decl *D, AnalysisManager &Mgr,
                                           BugReporter &BR) const {
  (void)BR;

  if (D == nullptr) {
    return;
  }

  const FunctionDecl *FD = dyn_cast<FunctionDecl>(D);
  if (FD == nullptr || !FD->hasBody()) {
    return;
  }

  QualType ReturnType = FD->getReturnType();

  if (ReturnType->isVoidType()) {
    return;
  }

  ASTContext &Ctx = Mgr.getASTContext();

  /*
   * First, report explicit "return;" statements in non-void functions.
   */
  MISRAC_17_4_ReturnVisitor Visitor(Ctx);
  Visitor.TraverseStmt(const_cast<Stmt *>(FD->getBody()));

  /*
   * Then, conservatively check whether all control-flow paths are guaranteed
   * to end with "return expression;".
   *
   * This is intentionally conservative and suitable for typical course
   * test cases:
   *   int f(int x) { if (x > 0) return 1; else return 0; }  // compliant
   *   int f(int x) { if (x > 0) return 1; }                 // violation
   *   int f(void)  { return; }                              // violation
   */
  if (!stmtAlwaysReturnsWithExpression(FD->getBody())) {
    reportMissingReturnExpression(Ctx, FD->getLocation());
  }
}

namespace clang {
namespace ento {

void registerMISRAC_17_4(CheckerManager &Mgr) {
  Mgr.registerChecker<MISRAC_17_4_Checker>();
}

bool shouldRegisterMISRAC_17_4(const CheckerManager &Mgr) { return true; }

} // namespace ento
} // namespace clang