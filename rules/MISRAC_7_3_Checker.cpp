#include "clang/AST/ASTContext.h"
#include "clang/AST/Expr.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Basic/Diagnostic.h"
#include "clang/Basic/SourceManager.h"
#include "clang/Lex/Lexer.h"
#include "clang/StaticAnalyzer/Checkers/BuiltinCheckerRegistration.h"
#include "clang/StaticAnalyzer/Core/BugReporter/BugReporter.h"
#include "clang/StaticAnalyzer/Core/Checker.h"
#include "clang/StaticAnalyzer/Core/CheckerManager.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/AnalysisManager.h"

using namespace clang;
using namespace ento;

namespace {

class MISRAC_7_3_Checker : public Checker<check::ASTCodeBody> {
public:
  void checkASTCodeBody(const Decl *D, AnalysisManager &Mgr,
                        BugReporter &BR) const;
};

class MISRAC_7_3_Visitor : public RecursiveASTVisitor<MISRAC_7_3_Visitor> {
public:
  explicit MISRAC_7_3_Visitor(ASTContext &Ctx) : Ctx(Ctx) {}

  bool VisitIntegerLiteral(IntegerLiteral *IL) {
    checkLiteralSuffix(IL);
    return true;
  }

  bool VisitFloatingLiteral(FloatingLiteral *FL) {
    checkLiteralSuffix(FL);
    return true;
  }

private:
  ASTContext &Ctx;

  void checkLiteralSuffix(const Expr *E) {
    if (E == nullptr) {
      return;
    }

    SourceManager &SM = Ctx.getSourceManager();
    const LangOptions &LangOpts = Ctx.getLangOpts();

    SourceLocation Begin = E->getBeginLoc();
    SourceLocation End = E->getEndLoc();

    if (Begin.isInvalid() || End.isInvalid()) {
      return;
    }

    if (Begin.isMacroID() || End.isMacroID()) {
      Begin = SM.getSpellingLoc(Begin);
      End = SM.getSpellingLoc(End);
    }

    if (Begin.isInvalid() || End.isInvalid()) {
      return;
    }

    SourceLocation EndOfToken =
        Lexer::getLocForEndOfToken(End, 0, SM, LangOpts);

    if (EndOfToken.isInvalid()) {
      return;
    }

    CharSourceRange Range = CharSourceRange::getCharRange(Begin, EndOfToken);
    StringRef Text = Lexer::getSourceText(Range, SM, LangOpts);

    if (Text.empty()) {
      return;
    }

    /*
     * MISRA C:2012 Rule 7.3
     * The lowercase character 'l' shall not be used in a literal suffix.
     *
     * Non-compliant examples:
     *   123l
     *   123ll
     *   1.0l
     *
     * Compliant examples:
     *   123L
     *   123LL
     *   1.0L
     */
    if (Text.find('l') == StringRef::npos) {
      return;
    }

    DiagnosticsEngine &DE = Ctx.getDiagnostics();
    unsigned DiagID = DE.getCustomDiagID(
        DiagnosticsEngine::Warning,
        "MISRA C:2012 Rule 7.3 violation: lowercase 'l' shall not be used "
        "in a literal suffix; use uppercase 'L' instead");

    DE.Report(Begin, DiagID);
  }
};

} // end anonymous namespace

void MISRAC_7_3_Checker::checkASTCodeBody(const Decl *D, AnalysisManager &Mgr,
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

  MISRAC_7_3_Visitor Visitor(Ctx);
  Visitor.TraverseStmt(const_cast<Stmt *>(FD->getBody()));
}

namespace clang {
namespace ento {

void registerMISRAC_7_3(CheckerManager &Mgr) {
  Mgr.registerChecker<MISRAC_7_3_Checker>();
}

bool shouldRegisterMISRAC_7_3(const CheckerManager &Mgr) { return true; }

} // namespace ento
} // namespace clang